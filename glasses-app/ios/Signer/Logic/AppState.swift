import Foundation

/// The one state the whole app shows (phone screen, DAT lens state line, optional message to
/// the core). It mirrors the contract vocabulary (CONTRACTS section 4) but is the app's own
/// type: `AppStateResolver` builds it from DAT permission, device presence, DAT error triage,
/// the events socket and what the core reported.
enum AppState: String, Equatable, CaseIterable {
  case off
  case connecting
  case on
  case paused
  case glassesOff = "glasses_off"
  case permissionDenied = "permission_denied"
  case coreDown = "core_down"

  init(lens: LensState) {
    switch lens {
    case .off: self = .off
    case .connecting: self = .connecting
    case .on: self = .on
    case .paused: self = .paused
    case .glassesOff: self = .glassesOff
    case .permissionDenied: self = .permissionDenied
    case .coreDown: self = .coreDown
    }
  }

  var lensState: LensState {
    switch self {
    case .off: return .off
    case .connecting: return .connecting
    case .on: return .on
    case .paused: return .paused
    case .glassesOff: return .glassesOff
    case .permissionDenied: return .permissionDenied
    case .coreDown: return .coreDown
    }
  }

  /// State line text (icon + word on screen, never colour alone).
  var label: String { lensState.label }

  /// One of the three triggerable D3 states (DECISION.md, J4): something is wrong and the
  /// wearer needs to know what to do.
  var isFault: Bool {
    switch self {
    case .glassesOff, .permissionDenied, .coreDown: return true
    default: return false
    }
  }

  /// Plain next step, shown under the state line on the lens (<= 2 lines x 24 chars) and on
  /// the phone. nil when nothing is wrong.
  var nextStep: String? {
    switch self {
    case .permissionDenied: return "Allow camera in Meta AI, then tap Start"
    case .glassesOff: return "Put your glasses on"
    case .coreDown: return "Reconnecting to laptop. Check USB cable"
    default: return nil
    }
  }

  /// Map a DAT error (text from `DatErrorTriage.describe`) to the state it causes, or nil
  /// when it does not change what the wearer sees.
  static func fromDatError(_ text: String) -> AppState? {
    switch DatErrorTriage.classify(text) {
    case .capabilityDenied, .permissionDenied: return .permissionDenied
    case .noDevice: return .glassesOff
    case .updateRequired, .thermalOrPower, .other: return nil
    }
  }
}

/// Camera permission as the app tracks it (granted in the Meta AI app, not by iOS).
enum CameraPermissionStatus: String, Equatable {
  case unknown, granted, denied
}

/// Everything the resolver looks at. Plain values, so each trigger is a unit test.
struct AppSignals: Equatable {
  /// What the core last said (or what the app set locally while starting): off, connecting,
  /// on, paused. Core-sent fault states are honoured too.
  var base: AppState = .off
  /// The wearer tapped Start and the stream has not ended.
  var running = false
  var cameraPermission: CameraPermissionStatus = .unknown
  /// No glasses paired/connected, the session failed with no eligible device, or the device
  /// ended the session. Sticky until the next Start or until a device shows up.
  var glassesOff = false
  /// The events socket has been down for more than 2 s (`CoreLinkMonitor`).
  var coreDown = false
  /// Demo and screenshot trigger from the debug menu. Wins over everything.
  var debugOverride: AppState?
}

extension AppSignals {
  /// A DAT error (text from `DatErrorTriage.describe`) changes the signals it maps to
  /// (permission denied, no device). Returns the state it caused, nil when it maps to none.
  @discardableResult
  mutating func apply(datError text: String) -> AppState? {
    let caused = AppState.fromDatError(text)
    switch caused {
    case .permissionDenied: cameraPermission = .denied
    case .glassesOff: glassesOff = true
    default: break
    }
    return caused
  }

  /// The DAT device list changed. Glasses back: clear the fault. Empty while running: glasses off.
  mutating func apply(deviceCount: Int) {
    if deviceCount > 0 {
      glassesOff = false
    } else if running {
      glassesOff = true
    }
  }

  /// The wearer taps Start: faults from the last attempt are forgotten, the checks run again.
  mutating func beginStart() {
    running = true
    glassesOff = false
    coreDown = false
    cameraPermission = .unknown
    base = .connecting
  }

  /// The run ended (stop, failed start, device ended the session). `byDevice` means the
  /// glasses ended it, which is the glasses-off case.
  mutating func end(byDevice: Bool) {
    running = false
    coreDown = false
    base = .off
    if byDevice { glassesOff = true }
  }
}

enum AppStateResolver {
  /// Precedence: debug override, then permission denied, then glasses off (both are things
  /// only the wearer can fix, and a core `on` must not wipe them), then core down (only while
  /// running; the socket is closed on purpose when idle), then what the core reported.
  static func resolve(_ s: AppSignals) -> AppState {
    if let o = s.debugOverride { return o }
    if s.cameraPermission == .denied { return .permissionDenied }
    if s.glassesOff { return .glassesOff }
    if s.running && s.coreDown { return .coreDown }
    return s.base
  }
}

/// Decides `core_down`: the events socket has been down for MORE than 2 s (CONTRACTS section
/// 4). The clock is injected (`now`, seconds), so it is unit-testable. Connect attempts of the
/// auto-reconnect loop do not restart the window; only a real open does.
struct CoreLinkMonitor: Equatable {
  static let downAfter: TimeInterval = 2.0

  let threshold: TimeInterval
  private(set) var downSince: TimeInterval?

  init(threshold: TimeInterval = CoreLinkMonitor.downAfter) {
    self.threshold = threshold
  }

  /// The events socket is not open (dropped, refused, still reconnecting).
  mutating func socketDown(at now: TimeInterval) {
    if downSince == nil { downSince = now }
  }

  /// The events socket opened.
  mutating func socketUp() { downSince = nil }

  /// Forget everything (the app stopped on purpose).
  mutating func reset() { downSince = nil }

  func isCoreDown(now: TimeInterval) -> Bool {
    guard let since = downSince else { return false }
    return now - since > threshold
  }

  /// Seconds until `isCoreDown` turns true, nil when the socket is up or already down for
  /// long enough. Used to schedule one re-evaluation instead of polling.
  func secondsUntilDown(now: TimeInterval) -> TimeInterval? {
    guard let since = downSince, !isCoreDown(now: now) else { return nil }
    return max(0, threshold - (now - since)) + 0.05
  }
}
