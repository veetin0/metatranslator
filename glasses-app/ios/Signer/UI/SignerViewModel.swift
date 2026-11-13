import Foundation
import MWDATCore
import Observation
import UIKit

/// Drives the spike screen and wires the repositories together. The Start flow follows the
/// DAT lifecycle (docs: develop/dat/lifecycle-events, samples/CameraAccess/CameraViewModel):
///   consent (POST /session/start) -> core sockets -> camera permission (Meta AI app)
///   -> DeviceSession .started -> camera stream -> stream .streaming -> display attach
///   -> display .started -> cards (throttled, only while streaming).
@MainActor
@Observable
final class SignerViewModel {
  static let coreURLKey = "signer.coreURL"

  // MARK: Collaborators
  let session: SessionRepository
  @ObservationIgnored private let camera: CameraRepository
  @ObservationIgnored private let display: DisplayRepository
  @ObservationIgnored private let mock: MockDeviceRepository
  @ObservationIgnored private let client: CoreClient
  @ObservationIgnored private let pipeline: FramePipeline
  @ObservationIgnored private let speech: SpeechService
  @ObservationIgnored private let recognizer: ReplyRecognizer
  /// Seconds clock for the core_down window; injectable.
  @ObservationIgnored private let now: () -> TimeInterval

  // MARK: Settings (screen)
  var coreURLText: String
  private(set) var coreURLValid = true
  var useFallbackPlan = false
  private(set) var mockEnabled: Bool
  var mockFeed: MockDeviceRepository.Feed = .clip

  // MARK: Live state (screen)
  private(set) var isRunning = false
  private(set) var streamPhase: StreamPhase = .stopped
  private(set) var displayState = "none"
  /// The one state shown on the phone and the lens state line (D3).
  private(set) var appState: AppState = .off
  var lensState: LensState { appState.lensState }
  /// Debug menu: the state forced for demo and screenshots, nil when none.
  var debugState: AppState? { signals.debugOverride }
  /// Reply box (hold to talk, typed fallback).
  var reply = ReplyComposer()
  let replySTTEnabled: Bool
  private(set) var framesLink: CoreClient.Link = .disconnected
  private(set) var eventsLink: CoreClient.Link = .disconnected
  private(set) var counters = FramePipeline.Snapshot(
    arrivedPerSecond: 0, sentPerSecond: 0, arrivedTotal: 0, sentTotal: 0, droppedTotal: 0,
    lastWidth: 0, lastHeight: 0, lastJpegBytes: 0, lastAckRttMs: nil, worstAckRttMs: 0)
  private(set) var captionsReceived = 0
  private(set) var lastCaption: CaptionEvent?
  private(set) var stats: StatsEvent?
  /// Receipt of the latest caption to the DAT send returning, includes the 500 ms throttle.
  private(set) var captionToLensMs: Double?
  /// Latest caption's core timestamp to phone arrival; approximate (needs synced clocks).
  private(set) var captionAgeMsApprox: Int64?
  private(set) var displaySendMs: Double?
  private(set) var previewCard: LensCard = .state(.off)
  private(set) var audioRoute = "unknown"
  private(set) var logLines: [String] = []

  var plan: StreamPlan { useFallbackPlan ? .fallback : .primary }
  var isStreaming: Bool { streamPhase == .streaming }

  // MARK: Private
  @ObservationIgnored private var currentSession: DeviceSession?
  @ObservationIgnored private var ring = LogRing()
  @ObservationIgnored private var currentCaption: CaptionEvent?
  @ObservationIgnored private var pinnedCard: LensCard?
  @ObservationIgnored private var captionReceivedAt: TimeInterval?
  @ObservationIgnored private var ticker: Task<Void, Never>?
  @ObservationIgnored private var signals = AppSignals()
  @ObservationIgnored private var coreMonitor = CoreLinkMonitor()
  @ObservationIgnored private var coreCheck: Task<Void, Never>?
  @ObservationIgnored private var reporter = StateReporter()
  @ObservationIgnored private var talkHeld = false

  init(
    session: SessionRepository, camera: CameraRepository, display: DisplayRepository,
    mock: MockDeviceRepository, client: CoreClient, pipeline: FramePipeline,
    speech: SpeechService, recognizer: ReplyRecognizer, mockEnabled: Bool, coreURL: String,
    replySTTEnabled: Bool = true,
    now: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }
  ) {
    self.recognizer = recognizer
    self.replySTTEnabled = replySTTEnabled
    self.now = now
    self.session = session
    self.camera = camera
    self.display = display
    self.mock = mock
    self.client = client
    self.pipeline = pipeline
    self.speech = speech
    self.mockEnabled = mockEnabled
    self.coreURLText = coreURL
    wire()
    ticker = Task { [weak self] in
      while !Task.isCancelled {
        try? await Task.sleep(nanoseconds: 1_000_000_000)
        self?.tick()
      }
    }
  }

  isolated deinit {
    ticker?.cancel()
    coreCheck?.cancel()
  }

  // MARK: Wiring

  private func wire() {
    SpikeLog.shared.setSink { [weak self] line in
      Task { @MainActor in self?.append(line) }
    }

    session.onSessionStarted = { [weak self] s in self?.sessionStarted(s) }
    session.onSessionEnded = { [weak self] byUs in self?.sessionEnded(byUs: byUs) }
    session.onError = { [weak self] text in self?.datError(text) }
    session.onDevicesChanged = { [weak self] count in
      guard let self else { return }
      self.signals.apply(deviceCount: count)
      self.recompute()
    }

    recognizer.onPartial = { [weak self] text in self?.reply.updatePartial(text) }
    recognizer.onFinal = { [weak self] text in
      guard let self, let req = self.reply.finishListening(finalText: text) else { return }
      self.post(req)
    }
    recognizer.onUnavailable = { [weak self] reason in self?.reply.speechUnavailable(reason) }

    camera.onFrameArrived = { [pipeline] in pipeline.noteArrived() }
    camera.onFrame = { [pipeline] jpeg, w, h in pipeline.submit(jpeg: jpeg, width: w, height: h) }
    camera.onStreamPhase = { [weak self] phase in
      Task { @MainActor in self?.streamPhaseChanged(phase) }
    }

    display.onDisplayState = { [weak self] state in
      Task { @MainActor in self?.displayState = state }
    }
    display.onSend = { [weak self] ms, error in
      Task { @MainActor in self?.displaySent(ms: ms, error: error) }
    }

    client.onEvent = { [weak self] event in
      Task { @MainActor in self?.handle(event) }
    }
    client.onAck = { [pipeline] seq in pipeline.noteAck(seq: seq) }
    client.onLink = { [weak self] socket, link in
      Task { @MainActor in self?.linkChanged(socket, link) }
    }
  }

  private func append(_ line: String) {
    ring.add(line)
    logLines = ring.lines
  }

  private func log(_ message: String) { SpikeLog.shared.add(message) }

  // MARK: Actions

  func register() { Task { await session.startRegistration() } }
  func unregister() { Task { await session.startUnregistration() } }

  func applyCoreURL() {
    coreURLValid = client.setBase(coreURLText)
    if coreURLValid {
      UserDefaults.standard.set(coreURLText, forKey: Self.coreURLKey)
      log("core URL = \(client.baseDescription)")
    } else {
      log("core URL not usable: \(coreURLText)")
    }
  }

  func checkCore() {
    applyCoreURL()
    Task { log(await client.health()) }
  }

  func startStream() {
    guard !isRunning else { return }
    isRunning = true
    signals.beginStart()
    coreMonitor.reset()
    applyCoreURL()
    pipeline.reset(source: mockEnabled ? .mock : .glasses)
    captionsReceived = 0
    // D3 glasses off: nothing to stream from. Say so before asking for any permission.
    if session.deviceIds.isEmpty {
      log("start: no glasses connected")
      abortStart(glassesOff: true)
      return
    }
    recompute()
    Task {
      // Start is consent: the core refuses frames unless its session is on (CONTRACTS section 2).
      log(await client.postSession(start: true, by: .app))
      client.connect()
      speech.configureAudioSession()
      guard await session.ensureCameraPermission() else {
        // D3 permission denied: the card says what to do (allow it in the Meta AI app).
        signals.cameraPermission = .denied
        abortStart()
        return
      }
      signals.cameraPermission = .granted
      recompute()
      if !session.startSession() {
        // The failure text decides: no eligible device is glasses off, denial is permission.
        if let text = session.lastError { signals.apply(datError: text) }
        abortStart()
        log(await client.postSession(start: false, by: .app))
      }
    }
  }

  /// A start that did not get going: back to idle, the fault (if any) stays on screen until
  /// the next Start.
  private func abortStart(glassesOff: Bool = false) {
    isRunning = false
    signals.end(byDevice: glassesOff)
    coreMonitor.reset()
    coreCheck?.cancel()
    client.disconnect()
    recompute()
  }

  func stopStream() {
    guard isRunning else { return }
    camera.stop()
    session.stopSession()
    // sessionEnded(byUs:) finishes the teardown when DAT reports STOPPED. If there never was
    // a session (stuck before it), clean up here.
    if !session.hasSession { sessionEnded(byUs: true) }
  }

  /// "Show Hello on display": queues the Hello card. It is sent only while the stream is
  /// `.streaming` and the display has started (the gate), and replaced by the next caption.
  func showHello() {
    pinnedCard = .hello
    log(isStreaming ? "hello: sending" : "hello: queued (sends once the stream is .streaming)")
    refreshLens()
  }

  func speakTest() {
    speech.speakTest()
    audioRoute = speech.routeDescription
  }

  func setMock(_ enabled: Bool) {
    UserDefaults.standard.set(enabled, forKey: MockDeviceRepository.defaultsKey)
    if enabled {
      mock.enableAndPair(feed: mockFeed)
    } else {
      mock.disable()
    }
    mockEnabled = enabled
  }

  func applyMockFeed() { mock.setFeed(mockFeed) }
  func startChromePreview() { Task { await mock.startChromePreviewServer() } }
  /// In-app view of the simulated display (Mock Device Kit), nil without a mock pair.
  func makeMockPreview() -> UIView? { mockEnabled ? mock.displayPreviewView() : nil }

  func clearLog() {
    ring.clear()
    logLines = []
  }

  // MARK: Session / camera / display callbacks

  private func sessionStarted(_ s: DeviceSession) {
    currentSession = s
    do {
      try camera.start(on: s, plan: plan)
    } catch {
      log("camera start failed: \(DatErrorTriage.describe(error))")
      session.stopSession()
    }
  }

  private func sessionEnded(byUs: Bool) {
    camera.stop()
    display.detach()
    currentSession = nil
    streamPhase = .stopped
    displayState = "none"
    isRunning = false
    pinnedCard = nil
    currentCaption = nil
    // A STOPPED the wearer did not ask for means the glasses ended it (taken off, dropped).
    signals.end(byDevice: !byUs)
    coreMonitor.reset()
    coreCheck?.cancel()
    recompute()
    speech.stop()
    Task {
      // A device-side STOPPED resets consent: tell the core (CONTRACTS section 2, by:"device").
      log(await client.postSession(start: false, by: byUs ? .app : .device))
      client.disconnect()
    }
  }

  private func streamPhaseChanged(_ phase: StreamPhase) {
    streamPhase = phase
    display.setStreamPhase(phase)
    if phase == .streaming, let s = currentSession {
      // The display is added next to the live camera on the same session: check (b).
      let result = display.attach(to: s)
      log("display attach result: \(result)")
      if signals.base == .connecting || signals.base == .off { signals.base = .on }
      recompute()
    }
  }

  private func displaySent(ms: Double, error: String?) {
    displaySendMs = ms
    if error == nil, let t0 = captionReceivedAt {
      captionToLensMs = (ProcessInfo.processInfo.systemUptime - t0) * 1000
    }
  }

  private func linkChanged(_ socket: CoreClient.Socket, _ link: CoreClient.Link) {
    switch socket {
    case .frames: framesLink = link
    case .events:
      eventsLink = link
      if link == .connected {
        coreMonitor.socketUp()
        reporter.reset()  // a fresh socket: the core has forgotten the app's state
      } else if isRunning {
        // Dropped, refused, or still retrying: the 2 s window starts at the first miss
        // and is not restarted by reconnect attempts. CoreClient reconnects on its own.
        coreMonitor.socketDown(at: now())
      }
      evaluateCoreLink()
    }
  }

  /// core_down only after the events socket has been down for more than 2 s.
  private func evaluateCoreLink() {
    coreCheck?.cancel()
    let t = now()
    signals.coreDown = coreMonitor.isCoreDown(now: t)
    recompute()
    if let wait = coreMonitor.secondsUntilDown(now: t) {
      coreCheck = Task { [weak self] in
        try? await Task.sleep(nanoseconds: UInt64(wait * 1_000_000_000))
        guard !Task.isCancelled else { return }
        self?.evaluateCoreLink()
      }
    }
  }

  // MARK: D3 states

  private func datError(_ text: String) {
    if signals.apply(datError: text) != nil { recompute() }
  }

  /// Debug menu: force a state on the phone and the lens (demo, screenshots). nil clears it.
  func triggerDebug(_ state: AppState?) {
    signals.debugOverride = state
    log("debug: state forced to \(state?.rawValue ?? "none")")
    recompute()
  }

  /// Resolves the one AppState from the signals, tells the core when it changed (flag-gated),
  /// and redraws the card.
  private func recompute() {
    let next = AppStateResolver.resolve(signals)
    if next != appState {
      log("app state: \(appState.rawValue) -> \(next.rawValue)")
      appState = next
      if let m = reporter.message(for: next, nowMs: Int64(Date().timeIntervalSince1970 * 1000)) {
        client.sendEvent(.appState(m))
      }
    }
    refreshLens()
  }

  // MARK: Reply (hold to talk, typed fallback)

  func replyPressBegan() {
    guard replySTTEnabled, !reply.isBusy, !talkHeld else { return }
    talkHeld = true
    reply.beginListening()
    Task {
      await recognizer.start()
      // Let go while the permission sheet was up: close the mic again.
      if !talkHeld { recognizer.stop() }
    }
  }

  func replyPressEnded() {
    guard talkHeld else { return }
    talkHeld = false
    reply.endListening()
    recognizer.stop()
  }

  func sendTypedReply() {
    guard let req = reply.submitTyped() else { return }
    post(req)
  }

  func dismissReplyMessage() { reply.clearMessage() }

  private func post(_ req: ReplyRequest) {
    Task {
      if let failure = await client.postReply(req) {
        reply.sendFailed(req, reason: failure)
      } else {
        reply.sendSucceeded(req)
      }
    }
  }

  // MARK: Core events

  private func handle(_ event: CoreEvent) {
    switch event {
    case .state(let e):
      signals.base = AppState(lens: e.state)
      if e.link == .slow { log("core: link slow") }
      recompute()
    case .caption(let c):
      captionsReceived += 1
      lastCaption = c
      currentCaption = c
      pinnedCard = nil
      captionReceivedAt = ProcessInfo.processInfo.systemUptime
      captionAgeMsApprox = CaptionAge.ms(captionTs: c.ts, nowMs: Int64(Date().timeIntervalSince1970 * 1000))
      log("caption \(c.id) [\(c.tier.rawValue) \(String(format: "%.2f", c.confidence))] \(c.text)")
      speech.speak(caption: c)
      audioRoute = speech.routeDescription
      refreshLens()
    case .retract(let id):
      if currentCaption?.id == id { currentCaption = nil }
      speech.retract(id: id)
      refreshLens()
    case .stats(let s):
      stats = s
      refreshLens()
    case .reply(let r):
      log("reply (\(r.source)): \(r.text)")
    case .partial(let p):
      _ = p  // card only; the lens ignores partials
    case .ack:
      break
    case .unknown(let type):
      log("core: unknown event type \(type)")
    }
  }

  /// Rebuilds the card and offers it to the display (gated + throttled there).
  private func refreshLens() {
    let card: LensCard
    if appState.isFault {
      // D3: state line plus the plain next step wins over a caption or the Hello card.
      card = .appState(appState, stats: stats)
    } else if let pinnedCard {
      card = pinnedCard
    } else if let c = currentCaption {
      card = .caption(c, state: lensState, stats: stats)
    } else {
      card = .state(lensState, stats: stats)
    }
    previewCard = card
    display.show(card)
  }

  private func tick() {
    counters = pipeline.snapshot()
    if speech.isOnBluetoothA2DP || audioRoute == "unknown" { audioRoute = speech.routeDescription }
  }
}
