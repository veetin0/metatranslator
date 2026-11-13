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
  private(set) var lensState: LensState = .off
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

  init(
    session: SessionRepository, camera: CameraRepository, display: DisplayRepository,
    mock: MockDeviceRepository, client: CoreClient, pipeline: FramePipeline,
    speech: SpeechService, mockEnabled: Bool, coreURL: String
  ) {
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

  isolated deinit { ticker?.cancel() }

  // MARK: Wiring

  private func wire() {
    SpikeLog.shared.setSink { [weak self] line in
      Task { @MainActor in self?.append(line) }
    }

    session.onSessionStarted = { [weak self] s in self?.sessionStarted(s) }
    session.onSessionEnded = { [weak self] byUs in self?.sessionEnded(byUs: byUs) }

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
    applyCoreURL()
    pipeline.reset(source: mockEnabled ? .mock : .glasses)
    captionsReceived = 0
    Task {
      // Start is consent: the core refuses frames unless its session is on (CONTRACTS section 2).
      log(await client.postSession(start: true, by: .app))
      client.connect()
      speech.configureAudioSession()
      guard await session.ensureCameraPermission() else {
        lensState = .permissionDenied
        refreshLens()
        isRunning = false
        client.disconnect()
        return
      }
      lensState = .connecting
      refreshLens()
      if !session.startSession() {
        isRunning = false
        client.disconnect()
        log(await client.postSession(start: false, by: .app))
      }
    }
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
    lensState = .off
    refreshLens()
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
      if lensState == .connecting || lensState == .off { lensState = .on }
      refreshLens()
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
      if link == .coreDown {
        lensState = .coreDown
        refreshLens()
      }
    }
  }

  // MARK: Core events

  private func handle(_ event: CoreEvent) {
    switch event {
    case .state(let e):
      lensState = e.state
      if e.link == .slow { log("core: link slow") }
      refreshLens()
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
    if let pinnedCard {
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
