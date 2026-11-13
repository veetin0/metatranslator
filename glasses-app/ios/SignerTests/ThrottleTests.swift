import XCTest

@testable import Signer

/// DAT Display sends: at most every 500 ms, only on change, trailing send for the last
/// change (CONTRACTS section 7). The clock is injected, so nothing here sleeps.
final class ThrottleTests: XCTestCase {
  func testFirstOfferIsSentImmediately() {
    var t = SendThrottle<String>()
    XCTAssertEqual(t.offer("a", now: 100), .send("a"))
  }

  func testSameContentIsDropped() {
    var t = SendThrottle<String>()
    _ = t.offer("a", now: 100)
    XCTAssertEqual(t.offer("a", now: 100.1), .drop)
    XCTAssertEqual(t.offer("a", now: 105), .drop, "unchanged stays dropped long after the window")
  }

  func testChangeInsideWindowWaitsUntilWindowEnds() {
    var t = SendThrottle<String>()
    _ = t.offer("a", now: 100)
    XCTAssertEqual(t.offer("b", now: 100.2), .wait(until: 100.5))
    XCTAssertEqual(t.pending, "b")
  }

  func testTrailingSendAfterWindow() {
    var t = SendThrottle<String>()
    _ = t.offer("a", now: 100)
    _ = t.offer("b", now: 100.2)
    XCTAssertNil(t.poll(now: 100.4), "still inside the window")
    XCTAssertEqual(t.poll(now: 100.5), "b")
    XCTAssertNil(t.poll(now: 101), "nothing left to send")
    XCTAssertEqual(t.lastSent, "b")
  }

  func testNewestChangeWinsInsideTheWindow() {
    var t = SendThrottle<String>()
    _ = t.offer("a", now: 0)
    _ = t.offer("b", now: 0.1)
    _ = t.offer("c", now: 0.2)
    XCTAssertEqual(t.poll(now: 0.5), "c")
  }

  func testChangingBackToWhatIsOnScreenCancelsThePendingSend() {
    var t = SendThrottle<String>()
    _ = t.offer("a", now: 0)
    _ = t.offer("b", now: 0.1)
    XCTAssertEqual(t.offer("a", now: 0.2), .drop)
    XCTAssertNil(t.pending)
    XCTAssertNil(t.poll(now: 1))
  }

  func testExactlyAtTheIntervalIsAllowed() {
    var t = SendThrottle<String>(minInterval: 0.5)
    _ = t.offer("a", now: 10)
    XCTAssertEqual(t.offer("b", now: 10.5), .send("b"))
  }

  func testMaxOneSendPerWindowUnderBurst() {
    var t = SendThrottle<Int>()
    var sends = 0
    var now = 0.0
    // 40 different values, one every 50 ms for 2 s, polling each tick.
    for i in 0..<40 {
      if case .send = t.offer(i, now: now) { sends += 1 }
      if t.poll(now: now) != nil { sends += 1 }
      now += 0.05
    }
    XCTAssertLessThanOrEqual(sends, 5, "2 s of changes may produce at most 5 sends at 500 ms")
    XCTAssertGreaterThanOrEqual(sends, 4)
  }

  func testResetMakesTheNextOfferImmediateEvenIfUnchanged() {
    var t = SendThrottle<String>()
    _ = t.offer("a", now: 100)
    t.reset()
    XCTAssertEqual(t.offer("a", now: 100.01), .send("a"), "display restarted, screen is blank")
  }

  func testLensCardsThrottleLikeAnyValue() {
    var t = SendThrottle<LensCard>()
    XCTAssertEqual(t.offer(.hello, now: 0), .send(.hello))
    XCTAssertEqual(t.offer(.hello, now: 0.1), .drop)
    XCTAssertEqual(t.offer(.state(.on), now: 0.1), .wait(until: 0.5))
  }

  // MARK: The "only while streaming" gate

  func testDisplayDrawsOnlyWhileStreamingAndStarted() {
    for phase in [StreamPhase.stopped, .waitingForDevice, .starting, .paused, .stopping] {
      XCTAssertFalse(DisplayGate.mayDraw(streamPhase: phase, displayStarted: true), "\(phase)")
    }
    XCTAssertFalse(DisplayGate.mayDraw(streamPhase: .streaming, displayStarted: false))
    XCTAssertTrue(DisplayGate.mayDraw(streamPhase: .streaming, displayStarted: true))
  }
}
