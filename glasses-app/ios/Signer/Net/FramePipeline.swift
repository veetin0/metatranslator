import Foundation

/// Glasses camera frame to core: numbers it, stamps it, packs it (CONTRACTS section 3) and
/// hands it to the `CoreClient`. Also keeps the spike counters: frames arriving from the
/// glasses per second (check (a)), frames sent to the core per second (check (d)), drops and
/// the ack round trip.
final class FramePipeline: @unchecked Sendable {
  struct Snapshot: Equatable {
    var arrivedPerSecond: Double
    var sentPerSecond: Double
    var arrivedTotal: Int
    var sentTotal: Int
    var droppedTotal: Int
    var lastWidth: Int
    var lastHeight: Int
    var lastJpegBytes: Int
    var lastAckRttMs: Double?
    var worstAckRttMs: Double
  }

  private let client: CoreClient
  private let lock = NSLock()
  private let clock: @Sendable () -> TimeInterval
  private var sequencer = FrameSequencer(source: .glasses)
  private var arrived = RateCounter()
  private var sent = RateCounter()
  private var acks = AckLatencyTracker()
  private var dropped = 0
  private var lastSize = (w: 0, h: 0)
  private var lastBytes = 0

  init(
    client: CoreClient,
    clock: @escaping @Sendable () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }
  ) {
    self.client = client
    self.clock = clock
  }

  /// A frame came off the glasses (before JPEG encoding).
  func noteArrived() {
    let now = clock()
    lock.withLock { arrived.tick(now: now) }
  }

  /// A JPEG is ready: pack it and send it. Returns whether the core socket took it.
  @discardableResult
  func submit(jpeg: Data, width: Int, height: Int) -> Bool {
    let now = clock()
    let wallMs = Int64(Date().timeIntervalSince1970 * 1000)
    let message: Data = lock.withLock {
      lastSize = (width, height)
      lastBytes = jpeg.count
      let header = sequencer.header(nowMs: wallMs, w: width, h: height)
      let packed = FramePacker.pack(header: header, jpeg: jpeg)
      acks.recordSent(seq: header.seq, now: now)
      return packed
    }
    let ok = client.sendFrame(message)
    lock.withLock {
      if ok { sent.tick(now: now) } else { dropped += 1 }
    }
    return ok
  }

  func noteAck(seq: Int) {
    let now = clock()
    lock.withLock { _ = acks.recordAck(seq: seq, now: now) }
  }

  func snapshot() -> Snapshot {
    let now = clock()
    return lock.withLock {
      Snapshot(
        arrivedPerSecond: arrived.rate(now: now), sentPerSecond: sent.rate(now: now),
        arrivedTotal: arrived.total, sentTotal: sent.total, droppedTotal: dropped,
        lastWidth: lastSize.w, lastHeight: lastSize.h, lastJpegBytes: lastBytes,
        lastAckRttMs: acks.lastRttMs, worstAckRttMs: acks.worstRttMs)
    }
  }

  /// New run. `source` is `.mock` when the Mock Device Kit feeds the camera, so frames from a
  /// simulated device are never labelled `glasses` (CONTRACTS section 3, R2 honesty).
  func reset(source: FrameSource = .glasses) {
    lock.withLock {
      sequencer = FrameSequencer(source: source)
      arrived.reset()
      sent.reset()
      acks.reset()
      dropped = 0
      lastSize = (0, 0)
      lastBytes = 0
    }
  }
}
