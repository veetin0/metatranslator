import Foundation
import os

/// Thread-safe spike log. Lines go to the unified log (Console.app, filter "Signer") and,
/// through `onLine`, to the screen. Callers on any thread; the view model hops to main.
final class SpikeLog: @unchecked Sendable {
  static let shared = SpikeLog()

  private let logger = Logger(subsystem: "com.signer.glasses", category: "spike")
  private let lock = NSLock()
  private var sink: (@Sendable (String) -> Void)?
  private let formatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "HH:mm:ss.SSS"
    return f
  }()

  func setSink(_ sink: (@Sendable (String) -> Void)?) {
    lock.withLock { self.sink = sink }
  }

  func add(_ message: String) {
    let line: String = lock.withLock { "\(formatter.string(from: Date())) \(message)" }
    logger.notice("\(message, privacy: .public)")
    let s = lock.withLock { sink }
    s?(line)
  }
}
