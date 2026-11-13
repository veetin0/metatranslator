import Foundation

/// Counts events per second over a sliding window (frames sent/s, frames received/s).
/// The clock is injected (`now` in seconds), so it is unit-testable.
struct RateCounter {
  let window: TimeInterval
  private var stamps: [TimeInterval] = []
  private(set) var total: Int = 0

  init(window: TimeInterval = 2.0) { self.window = window }

  mutating func tick(now: TimeInterval) {
    stamps.append(now)
    total += 1
    prune(now: now)
  }

  /// Events per second over the last `window` seconds.
  mutating func rate(now: TimeInterval) -> Double {
    prune(now: now)
    guard !stamps.isEmpty else { return 0 }
    return Double(stamps.count) / window
  }

  mutating func reset() {
    stamps.removeAll()
    total = 0
  }

  private mutating func prune(now: TimeInterval) {
    let cutoff = now - window
    if let first = stamps.firstIndex(where: { $0 > cutoff }) {
      stamps.removeFirst(first)
    } else {
      stamps.removeAll()
    }
  }
}

/// Round-trip time of frames: the core answers text `{"type":"ack","seq":n}` every 30 frames
/// on `/ws/frames` (CONTRACTS section 2), so `ack time - send time of seq n` is the phone to core
/// to phone RTT. This is not the "sign end to lens" latency of check (f); that one is measured
/// by hand (see the runbook) because it needs a human sign end.
struct AckLatencyTracker {
  private var sentAt: [Int: TimeInterval] = [:]
  private let capacity: Int
  private(set) var lastRttMs: Double?
  private(set) var worstRttMs: Double = 0

  init(capacity: Int = 128) { self.capacity = capacity }

  mutating func recordSent(seq: Int, now: TimeInterval) {
    sentAt[seq] = now
    if sentAt.count > capacity, let oldest = sentAt.keys.min() {
      sentAt.removeValue(forKey: oldest)
    }
  }

  @discardableResult
  mutating func recordAck(seq: Int, now: TimeInterval) -> Double? {
    guard let t0 = sentAt.removeValue(forKey: seq) else { return nil }
    let ms = (now - t0) * 1000
    lastRttMs = ms
    worstRttMs = max(worstRttMs, ms)
    return ms
  }

  mutating func reset() {
    sentAt.removeAll()
    lastRttMs = nil
    worstRttMs = 0
  }
}

/// Milliseconds between a caption's core timestamp and its arrival on the phone. Only
/// meaningful when the phone and the laptop clocks agree (both on network time), so the UI
/// labels it "approx". The lens leg (receipt to DAT send returned) is timed separately.
enum CaptionAge {
  static func ms(captionTs: Int64, nowMs: Int64) -> Int64 { nowMs - captionTs }
}

/// Bounded log for the spike screen: newest last.
struct LogRing {
  let capacity: Int
  private(set) var lines: [String] = []

  init(capacity: Int = 300) { self.capacity = capacity }

  mutating func add(_ line: String) {
    lines.append(line)
    if lines.count > capacity { lines.removeFirst(lines.count - capacity) }
  }

  mutating func clear() { lines.removeAll() }
}
