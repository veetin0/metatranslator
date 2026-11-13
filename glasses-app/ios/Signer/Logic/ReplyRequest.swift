import Foundation

/// Where a reply came from (CONTRACTS section 2, `POST /reply`).
enum ReplySource: String, Equatable {
  case stt
  case typed
}

/// One wearer reply to send to the core: `POST /reply {"text": "...", "source": "stt"|"typed"}`.
/// The core broadcasts it as a `reply` event and the card shows it.
struct ReplyRequest: Equatable {
  static let maxLength = 280

  let text: String
  let source: ReplySource

  /// nil when there is nothing to send (empty or whitespace only). Long text is cut at
  /// `maxLength` characters; a reply is a short line, not a document.
  init?(text: String, source: ReplySource) {
    let cleaned = text.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
    guard !cleaned.isEmpty else { return nil }
    self.text = String(cleaned.prefix(Self.maxLength))
    self.source = source
  }

  var jsonBody: Data {
    // JSONSerialization escapes quotes and unicode; sorted keys keep it deterministic.
    let obj: [String: String] = ["text": text, "source": source.rawValue]
    return (try? JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys])) ?? Data("{}".utf8)
  }

  func urlRequest(endpoints: CoreEndpoints, timeout: TimeInterval = 3) -> URLRequest {
    var req = URLRequest(url: endpoints.replyURL, timeoutInterval: timeout)
    req.httpMethod = "POST"
    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
    req.httpBody = jsonBody
    return req
  }
}

/// State of the reply box on the phone: hold-to-talk (Apple Speech) and the typed fallback.
/// Pure value type, so the flow is unit-testable without a microphone.
struct ReplyComposer: Equatable {
  enum Phase: Equatable {
    case idle
    /// Mic is open; `partial` shows the words as they are recognised.
    case listening
    /// Mic closed, waiting for the recogniser's final text.
    case processing
    case sending
    case sent(String)
    /// Speech is not available (permission denied, no recogniser); typing still works.
    case unavailable(String)
    case failed(String)
  }

  private(set) var phase: Phase = .idle
  private(set) var partial = ""
  var typed = ""

  var isBusy: Bool {
    switch phase {
    case .listening, .processing, .sending: return true
    default: return false
    }
  }

  var canSendTyped: Bool { !isBusy && ReplyRequest(text: typed, source: .typed) != nil }

  mutating func beginListening() {
    guard !isBusy else { return }
    partial = ""
    phase = .listening
  }

  mutating func updatePartial(_ text: String) {
    guard phase == .listening || phase == .processing else { return }
    partial = text
  }

  /// The wearer let go of the button.
  mutating func endListening() {
    guard phase == .listening else { return }
    phase = .processing
  }

  /// The recogniser finished (or timed out with the last partial). Returns the request to
  /// post, nil if nothing was heard.
  mutating func finishListening(finalText: String?) -> ReplyRequest? {
    guard phase == .listening || phase == .processing else { return nil }
    let text = (finalText?.isEmpty == false ? finalText : nil) ?? partial
    partial = ""
    guard let req = ReplyRequest(text: text, source: .stt) else {
      phase = .failed("Didn't hear anything. Hold the button and speak, or type below.")
      return nil
    }
    phase = .sending
    return req
  }

  /// "Send" on the typed field. Clears the field once the request is made.
  mutating func submitTyped() -> ReplyRequest? {
    guard !isBusy, let req = ReplyRequest(text: typed, source: .typed) else { return nil }
    typed = ""
    phase = .sending
    return req
  }

  mutating func sendSucceeded(_ req: ReplyRequest) { phase = .sent(req.text) }

  mutating func sendFailed(_ req: ReplyRequest, reason: String) {
    // Give typed text back so it is not lost.
    if req.source == .typed && typed.isEmpty { typed = req.text }
    phase = .failed("Not sent: \(reason)")
  }

  mutating func speechUnavailable(_ reason: String) {
    partial = ""
    phase = .unavailable(reason)
  }

  /// Back to idle, for dismissing a message.
  mutating func clearMessage() {
    if !isBusy { phase = .idle }
  }
}

/// `SIGNER_FLAGS` (CONTRACTS section 9) as the app can see it: the core reads it from its
/// environment, the app from a launch argument `--flags teach,reply_stt` or the same
/// environment variable. With no value (the normal phone case) reply STT is on.
enum AppFlags {
  /// App to core `state` message (CONTRACTS section 4 app state relay, approved by the lead
  /// 2026-11-14): the core passes it on to the card.
  static let sendStateToCore = true

  static func parse(_ raw: String?) -> Set<String> {
    guard let raw else { return [] }
    return Set(
      raw.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces).lowercased() }
        .filter { !$0.isEmpty })
  }

  static func replySTTEnabled(rawFlags: String?) -> Bool {
    let flags = parse(rawFlags)
    return flags.isEmpty || flags.contains("reply_stt")
  }

  static func current(arguments: [String] = ProcessInfo.processInfo.arguments,
                      environment: [String: String] = ProcessInfo.processInfo.environment) -> String? {
    if let i = arguments.firstIndex(of: "--flags"), arguments.indices.contains(i + 1) {
      return arguments[i + 1]
    }
    return environment["SIGNER_FLAGS"]
  }
}
