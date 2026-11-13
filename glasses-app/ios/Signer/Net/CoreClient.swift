import Foundation

/// WebSocket + HTTP client for the Signer core (CONTRACTS section 2).
///   `WS /ws/frames`  producer to core, binary frames (section 3); core answers text `ack`.
///   `WS /ws/events`  core to app, JSON text events (section 4); app sends `hello`.
///   `POST /session/start|stop` consent calls; `GET /health`.
/// Built on `URLSessionWebSocketTask`. `core_down` is produced here when the events socket
/// stays down for more than 2 s (CONTRACTS section 4: clients produce it, never the core).
final class CoreClient: NSObject, URLSessionWebSocketDelegate, @unchecked Sendable {
  enum Socket: String { case frames, events }
  enum Link: Equatable { case disconnected, connecting, connected, coreDown }

  var onEvent: (@Sendable (CoreEvent) -> Void)?
  var onAck: (@Sendable (Int) -> Void)?
  var onLink: (@Sendable (Socket, Link) -> Void)?

  /// Sends allowed in flight at once; more are dropped (a stale frame is worse than none,
  /// the core drops frames older than 300 ms).
  static let maxFramesInFlight = 4
  static let coreDownAfter: TimeInterval = 2.0
  static let reconnectDelay: TimeInterval = 1.0

  private let lock = NSLock()
  private var endpoints: CoreEndpoints
  private var wantConnected = false
  private var framesTask: URLSessionWebSocketTask?
  private var eventsTask: URLSessionWebSocketTask?
  private var framesInFlight = 0
  private var framesGivenUp = false  // 4403 consent_required: stop retrying until connect() again
  private var coreDownTimer: Task<Void, Never>?
  private let log = SpikeLog.shared
  private lazy var session: URLSession = {
    URLSession(configuration: .default, delegate: self, delegateQueue: nil)
  }()

  init(endpoints: CoreEndpoints = CoreEndpoints(CoreEndpoints.defaultBase)!) {
    self.endpoints = endpoints
    super.init()
  }

  var baseDescription: String { lock.withLock { endpoints.wsBase.absoluteString } }

  /// Returns false (and keeps the old URL) when the text is not a usable URL.
  @discardableResult
  func setBase(_ raw: String) -> Bool {
    guard let e = CoreEndpoints(raw) else { return false }
    lock.withLock { endpoints = e }
    return true
  }

  // MARK: Connect

  func connect() {
    lock.withLock {
      wantConnected = true
      framesGivenUp = false
    }
    open(.events)
    open(.frames)
  }

  func disconnect() {
    let tasks: [URLSessionWebSocketTask?] = lock.withLock {
      wantConnected = false
      defer {
        framesTask = nil
        eventsTask = nil
        framesInFlight = 0
        coreDownTimer?.cancel()
        coreDownTimer = nil
      }
      return [framesTask, eventsTask]
    }
    tasks.forEach { $0?.cancel(with: .normalClosure, reason: nil) }
    onLink?(.frames, .disconnected)
    onLink?(.events, .disconnected)
  }

  private func open(_ socket: Socket) {
    let (url, existing): (URL, URLSessionWebSocketTask?) = lock.withLock {
      switch socket {
      case .frames: return (endpoints.framesURL, framesTask)
      case .events: return (endpoints.eventsURL, eventsTask)
      }
    }
    if existing != nil { return }
    let task = session.webSocketTask(with: url)
    lock.withLock {
      switch socket {
      case .frames: framesTask = task
      case .events: eventsTask = task
      }
    }
    onLink?(socket, .connecting)
    log.add("core: connecting \(url.absoluteString)")
    task.resume()
    receive(task, socket)
  }

  // MARK: Frames out

  /// Queues one packed frame message. Returns false when it was dropped (no socket, or too
  /// many frames still in flight).
  @discardableResult
  func sendFrame(_ message: Data) -> Bool {
    let task: URLSessionWebSocketTask? = lock.withLock {
      guard let t = framesTask, framesInFlight < Self.maxFramesInFlight else { return nil }
      framesInFlight += 1
      return t
    }
    guard let task else { return false }
    task.send(.data(message)) { [weak self] error in
      guard let self else { return }
      self.lock.withLock { self.framesInFlight = max(0, self.framesInFlight - 1) }
      if let error { self.log.add("core: frame send failed: \(error.localizedDescription)") }
    }
    return true
  }

  func sendEvent(_ message: ClientMessage) {
    let task = lock.withLock { eventsTask }
    task?.send(.string(message.jsonString)) { [weak self] error in
      if let error { self?.log.add("core: event send failed: \(error.localizedDescription)") }
    }
  }

  // MARK: Receive

  private func receive(_ task: URLSessionWebSocketTask, _ socket: Socket) {
    task.receive { [weak self] result in
      guard let self else { return }
      switch result {
      case .failure(let error):
        self.socketEnded(task, socket, reason: error.localizedDescription)
      case .success(let message):
        switch message {
        case .string(let text): self.handle(text: text, on: socket)
        case .data(let data): self.handle(text: String(decoding: data, as: UTF8.self), on: socket)
        @unknown default: break
        }
        self.receive(task, socket)
      }
    }
  }

  private func handle(text: String, on socket: Socket) {
    do {
      let event = try CoreEvent.decode(line: text)
      if case .ack(let seq) = event {
        onAck?(seq)
      } else {
        onEvent?(event)
      }
    } catch {
      log.add("core: undecodable \(socket.rawValue) message: \(text.prefix(120))")
    }
  }

  private func isCurrent(_ task: URLSessionWebSocketTask, _ socket: Socket) -> Bool {
    lock.withLock { (socket == .frames ? framesTask : eventsTask) === task }
  }

  private func socketEnded(_ task: URLSessionWebSocketTask, _ socket: Socket, reason: String) {
    guard isCurrent(task, socket) else { return }
    let (want, giveUp): (Bool, Bool) = lock.withLock {
      switch socket {
      case .frames: framesTask = nil; framesInFlight = 0
      case .events: eventsTask = nil
      }
      return (wantConnected, socket == .frames && framesGivenUp)
    }
    log.add("core: \(socket.rawValue) socket ended: \(reason)")
    onLink?(socket, .disconnected)
    guard want, !giveUp else { return }
    if socket == .events { armCoreDownTimer() }
    Task { [weak self] in
      try? await Task.sleep(nanoseconds: UInt64(Self.reconnectDelay * 1_000_000_000))
      guard let self, self.lock.withLock({ self.wantConnected }) else { return }
      self.open(socket)
    }
  }

  private func armCoreDownTimer() {
    lock.withLock {
      guard coreDownTimer == nil else { return }
      coreDownTimer = Task { [weak self] in
        try? await Task.sleep(nanoseconds: UInt64(Self.coreDownAfter * 1_000_000_000))
        guard !Task.isCancelled, let self else { return }
        self.lock.withLock { self.coreDownTimer = nil }
        let stillDown = self.lock.withLock { self.eventsTask == nil }
        if stillDown { self.onLink?(.events, .coreDown) }
      }
    }
  }

  // MARK: URLSessionWebSocketDelegate

  func urlSession(
    _ session: URLSession, webSocketTask: URLSessionWebSocketTask,
    didOpenWithProtocol protocol: String?
  ) {
    let socket: Socket? = lock.withLock {
      if webSocketTask === framesTask { return .frames }
      if webSocketTask === eventsTask { return .events }
      return nil
    }
    guard let socket else { return }
    log.add("core: \(socket.rawValue) socket open")
    onLink?(socket, .connected)
    if socket == .events {
      lock.withLock {
        coreDownTimer?.cancel()
        coreDownTimer = nil
      }
      sendEvent(.hello(.app))
    }
  }

  func urlSession(
    _ session: URLSession, webSocketTask: URLSessionWebSocketTask,
    didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?
  ) {
    let socket: Socket? = lock.withLock {
      if webSocketTask === framesTask { return .frames }
      if webSocketTask === eventsTask { return .events }
      return nil
    }
    guard let socket else { return }
    let reasonText = reason.flatMap { String(data: $0, encoding: .utf8) } ?? ""
    if socket == .frames, closeCode.rawValue == CoreCloseCode.consentRequired {
      lock.withLock { framesGivenUp = true }
      log.add("core: frames closed 4403 consent_required: the core session is not on (POST /session/start)")
    }
    socketEnded(webSocketTask, socket, reason: "closed \(closeCode.rawValue) \(reasonText)")
  }

  // MARK: HTTP (consent and health)

  /// `POST /session/start` or `/session/stop` with `{"by": ...}`. Returns a short log line.
  func postSession(start: Bool, by: SessionBy) async -> String {
    let url = lock.withLock { start ? endpoints.sessionStartURL : endpoints.sessionStopURL }
    var req = URLRequest(url: url, timeoutInterval: 3)
    req.httpMethod = "POST"
    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
    req.httpBody = Data("{\"by\":\"\(by.rawValue)\"}".utf8)
    do {
      let (data, resp) = try await session.data(for: req)
      let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
      let body = String(decoding: data.prefix(160), as: UTF8.self)
      return "POST \(url.path) by=\(by.rawValue) -> \(code) \(body)"
    } catch {
      return "POST \(url.path) failed: \(error.localizedDescription)"
    }
  }

  /// `POST /reply {"text","source"}` (CONTRACTS section 2). Returns nil on success (2xx),
  /// else a short reason for the screen.
  func postReply(_ reply: ReplyRequest) async -> String? {
    let endpoints = lock.withLock { self.endpoints }
    do {
      let (_, resp) = try await session.data(for: reply.urlRequest(endpoints: endpoints))
      let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
      log.add("POST /reply source=\(reply.source.rawValue) -> \(code)")
      return (200..<300).contains(code) ? nil : "core answered \(code)"
    } catch {
      log.add("POST /reply failed: \(error.localizedDescription)")
      return "core not reachable"
    }
  }

  func health() async -> String {
    let url = lock.withLock { endpoints.healthURL }
    do {
      let (data, resp) = try await session.data(from: url)
      let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
      return "GET /health -> \(code) \(String(decoding: data.prefix(160), as: UTF8.self))"
    } catch {
      return "GET /health failed: \(error.localizedDescription)"
    }
  }
}
