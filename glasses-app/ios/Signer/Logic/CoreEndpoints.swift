import Foundation

/// Builds the core URLs (CONTRACTS section 2) from the one editable setting, the base URL.
/// Default `ws://172.20.10.2:8000` is the Mac on iPhone USB Personal Hotspot tethering.
struct CoreEndpoints: Equatable {
  static let defaultBase = "ws://172.20.10.2:8000"

  let wsBase: URL
  let httpBase: URL

  /// Accepts `ws://host:port`, `http://host:port`, or bare `host:port` / `host`
  /// (becomes `ws://host:8000` if no port). Returns nil for unusable input.
  init?(_ raw: String) {
    var text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    while text.hasSuffix("/") { text.removeLast() }
    guard !text.isEmpty else { return nil }
    if !text.contains("://") { text = "ws://" + text }
    guard var comps = URLComponents(string: text), let host = comps.host, !host.isEmpty else {
      return nil
    }
    var wsComps = comps
    var httpComps = comps
    switch comps.scheme?.lowercased() {
    case "ws", "http":
      wsComps.scheme = "ws"
      httpComps.scheme = "http"
      if comps.port == nil {  // the core's default port (SIGNER_PORT=8000)
        wsComps.port = 8000
        httpComps.port = 8000
      }
    case "wss", "https":  // e.g. a tunnel on 443: keep the URL as typed
      wsComps.scheme = "wss"
      httpComps.scheme = "https"
    default:
      return nil
    }
    comps.path = ""
    wsComps.path = ""
    httpComps.path = ""
    guard let ws = wsComps.url, let http = httpComps.url else { return nil }
    self.wsBase = ws
    self.httpBase = http
  }

  var framesURL: URL { wsBase.appendingPathComponent("ws/frames") }
  var eventsURL: URL { wsBase.appendingPathComponent("ws/events") }
  var healthURL: URL { httpBase.appendingPathComponent("health") }
  var sessionStartURL: URL { httpBase.appendingPathComponent("session/start") }
  var sessionStopURL: URL { httpBase.appendingPathComponent("session/stop") }
}

/// Who asks the core to start or stop (CONTRACTS section 2, `by`).
enum SessionBy: String {
  case card, app, idle, device
}

/// Close code the core uses when frames arrive without an `on` session (CONTRACTS section 2).
enum CoreCloseCode {
  static let consentRequired = 4403
}
