import Foundation

/// App to core state message (contract change PENDING lead approval):
/// `{"type":"state","state":"glasses_off"|"permission_denied"|"on","link":"ok","ts":ms,"from":"app"}`
/// sent on `/ws/events` when the app state changes. Behind `AppFlags.sendStateToCore`, OFF by
/// default, so today's core never sees it.
struct StateMessage: Codable, Equatable {
  enum Wire: String, Codable, Equatable {
    case on
    case glassesOff = "glasses_off"
    case permissionDenied = "permission_denied"
  }

  var type = "state"
  var state: Wire
  var link = "ok"
  var ts: Int64
  var from = "app"

  /// Only these three app states are reportable; off, connecting, paused are the core's own
  /// business and core_down cannot be sent (the socket is the thing that is down).
  init?(appState: AppState, nowMs: Int64) {
    switch appState {
    case .on: state = .on
    case .glassesOff: state = .glassesOff
    case .permissionDenied: state = .permissionDenied
    case .off, .connecting, .paused, .coreDown: return nil
    }
    ts = nowMs
  }

  var jsonString: String {
    let enc = JSONEncoder()
    enc.outputFormatting = [.sortedKeys]
    guard let data = try? enc.encode(self) else { return "{}" }
    return String(decoding: data, as: UTF8.self)
  }
}

/// Decides when to send a `StateMessage`: only on a change of app state, only for reportable
/// states, and only when the flag is on.
struct StateReporter: Equatable {
  let enabled: Bool
  private(set) var lastReported: AppState?

  init(enabled: Bool = AppFlags.sendStateToCore) {
    self.enabled = enabled
  }

  mutating func message(for state: AppState, nowMs: Int64) -> StateMessage? {
    guard enabled, state != lastReported else { return nil }
    lastReported = state
    return StateMessage(appState: state, nowMs: nowMs)
  }

  /// After a reconnect the core has forgotten the app's state: report again.
  mutating func reset() { lastReported = nil }
}
