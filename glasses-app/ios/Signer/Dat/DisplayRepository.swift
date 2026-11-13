import Foundation
import MWDATCore
import MWDATDisplay

/// DAT Display card while the camera streams, on the same session as the camera (check (b)).
/// Real DAT calls (docs: develop/dat/display-overview, samples/DisplayAccess, BirdSpotter's
/// DatGlassesSessionRepository/DatGlassesDisplayRepository):
///   device.supportsDisplay()
///   session.addDisplay() -> Display, display.statePublisher, display.start()
///   display.send(FlexBox { Text ... })  (replaces the whole screen), display.clearDisplay()
///
/// Rules from CONTRACTS section 7: at most one send per 500 ms, only when the card changed,
/// and only while the camera stream is `.streaming`. The newest wanted card is kept and sent
/// when the window passes (trailing send), or when the gate opens.
///
/// This file must not import SwiftUI: `MWDATDisplay.Text` would clash with `SwiftUI.Text`.
final class DisplayRepository: @unchecked Sendable {
  enum AttachResult: Equatable {
    case attached
    case alreadyAttached
    case noDisplayOnDevice
    case failed(String)
  }

  /// (send duration in ms, error text or nil), after each send returns.
  var onSend: (@Sendable (_ ms: Double, _ error: String?) -> Void)?
  var onDisplayState: (@Sendable (String) -> Void)?

  private let lock = NSLock()
  private let clock: @Sendable () -> TimeInterval
  private let interval: TimeInterval
  private var display: Display?
  private var displayStarted = false
  private var streamPhase: StreamPhase = .stopped
  private var throttle: SendThrottle<LensCard>
  private var wanted: LensCard?
  private var trailing: Task<Void, Never>?
  private let tokens = ListenerTokenBag()
  private let log = SpikeLog.shared

  init(
    minInterval: TimeInterval = 0.5,
    clock: @escaping @Sendable () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }
  ) {
    self.interval = minInterval
    self.clock = clock
    self.throttle = SendThrottle(minInterval: minInterval)
  }

  var isStarted: Bool { lock.withLock { displayStarted } }

  // MARK: Attach / detach

  /// Adds the display capability to the (started) session. Call once the camera stream is
  /// `.streaming`, so the display is added next to a live camera: that pairing is the spike.
  @discardableResult
  func attach(to session: DeviceSession) -> AttachResult {
    if lock.withLock({ display != nil }) { return .alreadyAttached }
    guard session.device?.supportsDisplay() == true else {
      log.add("display: this device has no display (Fallback C territory)")
      return .noDisplayOnDevice
    }
    let d: Display
    do {
      d = try session.addDisplay()
    } catch {
      let text = DatErrorTriage.describe(error)
      log.add("display: addDisplay failed while camera streams: \(text)")
      if DatErrorTriage.classify(text) == .capabilityDenied {
        log.add("!! CAPABILITY_DENIED suspected on the display: report to Meta immediately")
      }
      return .failed(text)
    }
    lock.withLock {
      display = d
      displayStarted = false
      throttle.reset()
    }
    d.statePublisher.listen { [weak self] state in
      self?.displayStateChanged(state)
    }.store(in: tokens)
    d.start()
    log.add("display: attached next to the camera, starting")
    return .attached
  }

  func detach() {
    let (d, task): (Display?, Task<Void, Never>?) = lock.withLock {
      defer {
        display = nil
        displayStarted = false
        trailing = nil
        wanted = nil
        throttle.reset()
      }
      return (display, trailing)
    }
    task?.cancel()
    tokens.clear()
    d?.stop()
  }

  // MARK: Gate and sending

  func setStreamPhase(_ phase: StreamPhase) {
    lock.withLock { streamPhase = phase }
    evaluate()
  }

  /// Ask for this card to be on the lens. Nothing is sent unless the stream is `.streaming`,
  /// the display has started, the card differs from the last one sent and 500 ms have passed.
  func show(_ card: LensCard) {
    lock.withLock { wanted = card }
    evaluate()
  }

  func clear() {
    let d = lock.withLock { () -> Display? in
      wanted = nil
      throttle.reset()
      return display
    }
    guard let d else { return }
    Task { try? await d.clearDisplay() }
  }

  private func displayStateChanged(_ state: DisplayState) {
    let started = state == .started
    lock.withLock {
      displayStarted = started
      if !started { throttle.reset() }  // blank again after a restart
    }
    log.add("display state: \(state)")
    onDisplayState?(String(describing: state))
    evaluate()
  }

  private func evaluate() {
    enum Action { case none, send(LensCard, Display), schedule(TimeInterval) }
    let action: Action = lock.withLock {
      guard
        let card = wanted, let d = display,
        DisplayGate.mayDraw(streamPhase: streamPhase, displayStarted: displayStarted)
      else { return .none }
      let now = clock()
      switch throttle.offer(card, now: now) {
      case .send(let c): return .send(c, d)
      case .wait(let until): return .schedule(max(0.01, until - now))
      case .drop: return .none
      }
    }
    switch action {
    case .none:
      break
    case .send(let card, let d):
      Task { await self.send(card, on: d) }
    case .schedule(let delay):
      scheduleTrailing(after: delay)
    }
  }

  private func scheduleTrailing(after delay: TimeInterval) {
    lock.withLock {
      guard trailing == nil else { return }
      trailing = Task { [weak self] in
        try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
        guard !Task.isCancelled, let self else { return }
        self.lock.withLock { self.trailing = nil }
        self.evaluate()
      }
    }
  }

  private func send(_ card: LensCard, on d: Display) async {
    let t0 = clock()
    do {
      try await d.send(card.datView)
      let ms = (clock() - t0) * 1000
      log.add("display: sent \"\(card.lines.isEmpty ? card.stateLine : card.lines.joined(separator: " / "))\" in \(Int(ms)) ms")
      onSend?(ms, nil)
    } catch {
      let text = DatErrorTriage.describe(error)
      log.add("display: send failed: \(text)")
      onSend?((clock() - t0) * 1000, text)
    }
  }
}

extension LensTone.Slot {
  fileprivate var dat: TextColor {
    switch self {
    case .primary: return .primary
    case .secondary: return .secondary
    }
  }
}

extension LensCard {
  /// DESIGN.md lens card on DAT components: state line top (meta), caption lines (heading, at
  /// most 2), footer readout (meta). Black is transparent on the additive display, so no
  /// background is drawn. Amber is not available on DAT `Text`: the "?" prefix carries "unsure".
  var datView: FlexBox {
    FlexBox(direction: .column, spacing: 12, alignment: .start, crossAlignment: .center) {
      MWDATDisplay.Text(stateLine, style: .meta, color: .secondary)
      for line in lines {
        MWDATDisplay.Text(line, style: .heading, color: tone.datSlot.dat)
      }
      if let footer {
        MWDATDisplay.Text(footer, style: .meta, color: .secondary)
      }
    }
    .padding(16)
  }
}
