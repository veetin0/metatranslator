import Foundation
import MWDATCore
import Observation

/// Registration, camera permission and the one `DeviceSession`, following BirdSpotter's
/// session repository and CameraAccess's view models (samples/CameraAccess/.../WearablesViewModel.swift,
/// CameraViewModel.swift). Real DAT calls:
///   Wearables.shared.registrationStateStream() / startRegistration() / handleUrl(_:)
///   Wearables.shared.devicesStream() / deviceForIdentifier(_:)
///   Wearables.shared.checkPermissionStatus(.camera) / requestPermission(.camera)
///   Wearables.shared.createSession(deviceSelector:) -> DeviceSession, session.start()
///   session.statePublisher / errorPublisher, session.stop()
@MainActor
@Observable
final class SessionRepository {
  enum CameraPermission: String { case unknown, granted, denied }

  struct DeviceSummary: Equatable {
    var name: String
    var link: String
    var batteryPercent: Int?
    var thermal: String
    var compatibility: String
    var worn: String
    var hinge: String
    var supportsDisplay: Bool
  }

  private(set) var registrationState: RegistrationState
  private(set) var deviceIds: [DeviceIdentifier]
  private(set) var sessionState: DeviceSessionState = .idle
  private(set) var cameraPermission: CameraPermission = .unknown
  private(set) var device: DeviceSummary?
  private(set) var lastError: String?

  private static let grantedKey = "signer.cameraGranted"

  /// The session reached `.started`: attach the camera now.
  @ObservationIgnored var onSessionStarted: ((DeviceSession) -> Void)?
  /// The session ended (STOPPED), by us or by the device. `byUs` is true after `stopSession()`.
  @ObservationIgnored var onSessionEnded: ((_ byUs: Bool) -> Void)?
  /// Every session / permission / registration error as verbatim text, for the app state
  /// mapping (`AppSignals.apply(datError:)`).
  @ObservationIgnored var onError: ((String) -> Void)?
  /// The DAT device list changed (glasses paired, connected, gone).
  @ObservationIgnored var onDevicesChanged: ((Int) -> Void)?

  @ObservationIgnored private let wearables: WearablesInterface
  /// Held from init (CameraAccess pattern): a selector built at tap time has not yet seen
  /// the device stream and the session fails `noEligibleDevice`.
  @ObservationIgnored private let selector: AutoDeviceSelector
  @ObservationIgnored private var session: DeviceSession?
  @ObservationIgnored private var stoppedByUs = false
  @ObservationIgnored private let sessionTokens = ListenerTokenBag()
  @ObservationIgnored private let deviceTokens = ListenerTokenBag()
  @ObservationIgnored private var registrationTask: Task<Void, Never>?
  @ObservationIgnored private var devicesTask: Task<Void, Never>?
  @ObservationIgnored private let log = SpikeLog.shared

  init(wearables: WearablesInterface = Wearables.shared) {
    self.wearables = wearables
    self.selector = AutoDeviceSelector(wearables: wearables)
    self.registrationState = wearables.registrationState
    self.deviceIds = wearables.devices

    registrationTask = Task { [weak self] in
      for await state in wearables.registrationStateStream() {
        guard let self else { return }
        self.registrationState = state
        self.log.add("registration: \(state.description)")
      }
    }
    devicesTask = Task { [weak self] in
      for await ids in wearables.devicesStream() {
        guard let self else { return }
        self.deviceIds = ids
        self.log.add("devices: \(ids.isEmpty ? "none" : ids.joined(separator: ", "))")
        self.watchFirstDevice(ids)
        self.onDevicesChanged?(ids.count)
      }
    }
    watchFirstDevice(deviceIds)
  }

  isolated deinit {
    registrationTask?.cancel()
    devicesTask?.cancel()
    session?.stop()
  }

  // MARK: Registration (Meta AI app handoff, callback via signer://)

  func startRegistration() async {
    guard registrationState != .registering else { return }
    do {
      try await wearables.startRegistration()
    } catch {
      note("registration failed: \(DatErrorTriage.describe(error))")
    }
  }

  func startUnregistration() async {
    do {
      try await wearables.startUnregistration()
    } catch {
      note("unregistration failed: \(DatErrorTriage.describe(error))")
    }
  }

  /// Call from `.onOpenURL`: the SDK consumes its own callback URLs.
  func handle(url: URL) async {
    do {
      let handled = try await wearables.handleUrl(url)
      log.add("opened by URL \(url.scheme ?? "?")://\(url.host ?? "") handled=\(handled)")
    } catch {
      note("handleUrl failed: \(DatErrorTriage.describe(error))")
    }
  }

  // MARK: Camera permission (granted in the Meta AI app, not by iOS)

  /// `checkPermissionStatus` is a query; `requestPermission` hands over to the Meta AI app
  /// (allow always / once / deny) and returns when the wearer comes back.
  func ensureCameraPermission() async -> Bool {
    do {
      if try await wearables.checkPermissionStatus(.camera) == .granted {
        cameraPermission = .granted
        return true
      }
    } catch {
      log.add("camera permission check: \(DatErrorTriage.describe(error)) (will request)")
    }
    // Meta AI answered "allow always" earlier but the query does not report it: do not send the
    // wearer through Meta AI again on every Start. A real denial clears this (below).
    if UserDefaults.standard.bool(forKey: Self.grantedKey) {
      log.add("camera permission: query not granted, using the earlier grant")
      cameraPermission = .granted
      return true
    }
    do {
      let result = try await wearables.requestPermission(.camera)
      cameraPermission = result == .granted ? .granted : .denied
      UserDefaults.standard.set(result == .granted, forKey: Self.grantedKey)
      log.add("camera permission request: \(result)")
      return result == .granted
    } catch {
      cameraPermission = .denied
      note("camera permission request failed: \(DatErrorTriage.describe(error))")
      return false
    }
  }

  // MARK: Session

  var hasSession: Bool {
    switch sessionState {
    case .starting, .started, .paused, .stopping: return true
    case .idle, .stopped: return false
    }
  }

  /// Creates and starts the `DeviceSession`; `onSessionStarted` fires on `.started`.
  /// Returns false when it could not be created (reason in the log and `lastError`).
  @discardableResult
  func startSession() -> Bool {
    guard !hasSession else { return false }
    stoppedByUs = false
    do {
      let s = try wearables.createSession(deviceSelector: selector)
      session = s
      observe(s)
      sessionState = .starting
      log.add("session: starting on \(s.deviceId)")
      try s.start()
      return true
    } catch {
      note("session start failed: \(DatErrorTriage.describe(error))")
      cleanupSession()
      sessionState = .idle
      return false
    }
  }

  func stopSession() {
    guard let session else { return }
    stoppedByUs = true
    sessionState = .stopping
    session.stop()
  }

  // MARK: Observation

  private func observe(_ s: DeviceSession) {
    s.statePublisher.listen { [weak self] state in
      Task { @MainActor in self?.handle(sessionState: state, session: s) }
    }.store(in: sessionTokens)
    s.errorPublisher.listen { [weak self] error in
      Task { @MainActor in self?.handle(sessionError: error) }
    }.store(in: sessionTokens)
  }

  private func handle(sessionState state: DeviceSessionState, session s: DeviceSession) {
    sessionState = state
    log.add("session: \(state.description)")
    switch state {
    case .started:
      onSessionStarted?(s)
    case .stopped:
      let byUs = stoppedByUs
      cleanupSession()
      onSessionEnded?(byUs)
    default:
      break
    }
  }

  private func handle(sessionError error: DeviceSessionError) {
    // Verbatim, so CAPABILITY_DENIED (server-side gating) is visible if it ever shows up.
    note("session error: \(DatErrorTriage.describe(error))")
  }

  private func cleanupSession() {
    sessionTokens.clear()
    session = nil
  }

  // MARK: Device info (battery, thermal for check (f))

  private func watchFirstDevice(_ ids: [DeviceIdentifier]) {
    deviceTokens.clear()
    guard let id = ids.first, let d = wearables.deviceForIdentifier(id) else {
      device = nil
      return
    }
    device = summary(of: d, state: nil)
    d.addDeviceStateListener { [weak self] state in
      Task { @MainActor in self?.device = self?.summary(of: d, state: state) }
    }.store(in: deviceTokens)
  }

  private func summary(of d: Device, state: DeviceState?) -> DeviceSummary {
    DeviceSummary(
      name: d.nameOrId(),
      link: String(describing: state?.linkState ?? d.linkState),
      batteryPercent: state?.batteryLevel ?? d.batteryLevel,
      thermal: String(describing: state?.thermalLevel ?? d.thermalLevel),
      compatibility: String(describing: state?.compatibility ?? d.compatibility()),
      worn: String(describing: state?.donState ?? d.donState),
      hinge: String(describing: state?.hingeState ?? d.hingeState),
      supportsDisplay: d.supportsDisplay())
  }

  private func note(_ message: String) {
    lastError = message
    log.add(message)
    onError?(message)
    if DatErrorTriage.classify(message) == .permissionDenied {
      UserDefaults.standard.set(false, forKey: Self.grantedKey)  // stale grant: ask again next Start
    }
    if DatErrorTriage.classify(message) == .capabilityDenied {
      log.add("!! CAPABILITY_DENIED suspected: report to Meta (device, app version, time) immediately")
    }
  }
}
