import Foundation

/// Rate limit for DAT Display sends (CONTRACTS section 7, DESIGN.md Motion).
/// Every send replaces the whole screen, so: at most one send per `minInterval` (500 ms),
/// nothing when the content did not change, and a trailing send when a change arrives
/// inside the window (otherwise the last caption would never be shown).
///
/// Pure value type with an injected clock (`now` is passed in, in seconds), so it is
/// unit-testable. Not thread-safe: the owner serialises access.
struct SendThrottle<Value: Equatable> {
  enum Decision: Equatable {
    /// Send this value now.
    case send(Value)
    /// Changed inside the window: it is kept as the pending trailing send; call `poll`
    /// at or after `until` (seconds on the same clock).
    case wait(until: TimeInterval)
    /// Same as what the screen already shows (or nothing to do).
    case drop
  }

  let minInterval: TimeInterval
  private(set) var lastSent: Value?
  private(set) var lastSentAt: TimeInterval?
  private(set) var pending: Value?

  init(minInterval: TimeInterval = 0.5) {
    self.minInterval = minInterval
  }

  mutating func offer(_ value: Value, now: TimeInterval) -> Decision {
    if value == lastSent {
      // Back to what is on screen: any pending change is obsolete.
      pending = nil
      return .drop
    }
    if let at = lastSentAt, now - at < minInterval {
      pending = value
      return .wait(until: at + minInterval)
    }
    commit(value, now: now)
    return .send(value)
  }

  /// Returns the pending trailing value once the window has passed.
  mutating func poll(now: TimeInterval) -> Value? {
    guard let value = pending else { return nil }
    if let at = lastSentAt, now - at < minInterval { return nil }
    commit(value, now: now)
    return value
  }

  /// Forget everything: the next offer is sent at once. Call when the display session
  /// restarts, because the screen is blank again.
  mutating func reset() {
    lastSent = nil
    lastSentAt = nil
    pending = nil
  }

  private mutating func commit(_ value: Value, now: TimeInterval) {
    lastSent = value
    lastSentAt = now
    pending = nil
  }
}
