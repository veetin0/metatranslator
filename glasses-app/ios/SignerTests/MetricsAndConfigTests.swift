import XCTest

@testable import Signer

final class MetricsAndConfigTests: XCTestCase {
  // MARK: RateCounter

  func testRateCountsEventsInTheWindow() {
    var r = RateCounter(window: 2)
    for i in 0..<20 { r.tick(now: Double(i) * 0.1) }  // 10 per second for 2 s
    XCTAssertEqual(r.rate(now: 1.9), 10, accuracy: 0.6)
    XCTAssertEqual(r.total, 20)
  }

  func testRateDecaysToZeroWhenEventsStop() {
    var r = RateCounter(window: 2)
    r.tick(now: 0)
    r.tick(now: 0.5)
    XCTAssertEqual(r.rate(now: 10), 0)
    XCTAssertEqual(r.total, 2, "the total never decays")
  }

  func testRateReset() {
    var r = RateCounter()
    r.tick(now: 1)
    r.reset()
    XCTAssertEqual(r.total, 0)
    XCTAssertEqual(r.rate(now: 1), 0)
  }

  // MARK: Ack latency

  func testAckRoundTrip() {
    var a = AckLatencyTracker()
    a.recordSent(seq: 29, now: 10.000)
    XCTAssertEqual(a.recordAck(seq: 29, now: 10.085) ?? -1, 85, accuracy: 0.01)
    XCTAssertEqual(a.lastRttMs ?? -1, 85, accuracy: 0.01)
  }

  func testAckForUnknownSeqIsIgnoredAndWorstIsKept() {
    var a = AckLatencyTracker()
    XCTAssertNil(a.recordAck(seq: 5, now: 1))
    a.recordSent(seq: 1, now: 0)
    a.recordSent(seq: 2, now: 0)
    a.recordAck(seq: 1, now: 0.3)
    a.recordAck(seq: 2, now: 0.1)
    XCTAssertEqual(a.worstRttMs, 300, accuracy: 0.01)
    XCTAssertEqual(a.lastRttMs ?? -1, 100, accuracy: 0.01)
  }

  func testAckTrackerForgetsOldestBeyondCapacity() {
    var a = AckLatencyTracker(capacity: 3)
    for s in 0..<5 { a.recordSent(seq: s, now: Double(s)) }
    XCTAssertNil(a.recordAck(seq: 0, now: 10), "seq 0 was evicted")
    XCTAssertNotNil(a.recordAck(seq: 4, now: 10))
  }

  func testCaptionAge() {
    XCTAssertEqual(CaptionAge.ms(captionTs: 1_000, nowMs: 1_250), 250)
  }

  // MARK: LogRing

  func testLogRingKeepsTheNewestLines() {
    var l = LogRing(capacity: 3)
    for i in 1...5 { l.add("l\(i)") }
    XCTAssertEqual(l.lines, ["l3", "l4", "l5"])
    l.clear()
    XCTAssertTrue(l.lines.isEmpty)
  }

  // MARK: Core URL

  func testDefaultCoreURLIsTheTetheredMac() throws {
    XCTAssertEqual(CoreEndpoints.defaultBase, "ws://172.20.10.2:8000")
    let e = try XCTUnwrap(CoreEndpoints(CoreEndpoints.defaultBase))
    XCTAssertEqual(e.framesURL.absoluteString, "ws://172.20.10.2:8000/ws/frames")
    XCTAssertEqual(e.eventsURL.absoluteString, "ws://172.20.10.2:8000/ws/events")
    XCTAssertEqual(e.healthURL.absoluteString, "http://172.20.10.2:8000/health")
    XCTAssertEqual(e.sessionStartURL.absoluteString, "http://172.20.10.2:8000/session/start")
    XCTAssertEqual(e.sessionStopURL.absoluteString, "http://172.20.10.2:8000/session/stop")
  }

  func testCoreURLNormalisation() throws {
    XCTAssertEqual(try XCTUnwrap(CoreEndpoints("192.168.1.5")).wsBase.absoluteString, "ws://192.168.1.5:8000")
    XCTAssertEqual(try XCTUnwrap(CoreEndpoints("mac.local:9000/")).wsBase.absoluteString, "ws://mac.local:9000")
    XCTAssertEqual(try XCTUnwrap(CoreEndpoints("http://10.0.0.2:8000")).wsBase.absoluteString, "ws://10.0.0.2:8000")
    XCTAssertEqual(try XCTUnwrap(CoreEndpoints("wss://x.example.com")).httpBase.absoluteString, "https://x.example.com")
    XCTAssertNil(CoreEndpoints(""))
    XCTAssertNil(CoreEndpoints("   "))
    XCTAssertNil(CoreEndpoints("ftp://host"))
  }

  func testConsentRequiredCloseCode() {
    XCTAssertEqual(CoreCloseCode.consentRequired, 4403)
    XCTAssertEqual(SessionBy.device.rawValue, "device")
  }

  // MARK: Stream plan

  func testPrimaryPlanIsMediumAt24() {
    XCTAssertEqual(StreamPlan.primary.resolution, .medium)
    XCTAssertEqual(StreamPlan.primary.frameRate, 24)
    XCTAssertEqual(StreamPlan.primary.expectedSize.w, 504)
    XCTAssertEqual(StreamPlan.primary.expectedSize.h, 896)
  }

  func testFallbackPlanIsLowAtSeven() {
    XCTAssertEqual(StreamPlan.fallback.resolution, .low)
    XCTAssertEqual(StreamPlan.fallback.frameRate, 7)
    XCTAssertEqual(StreamPlan.fallback.expectedSize.w, 360)
    XCTAssertEqual(StreamPlan.fallback.expectedSize.h, 640)
  }

  func testFrameRateSnapsDownToAValidDATRate() {
    XCTAssertEqual(StreamPlan.snapFrameRate(15), 15)
    XCTAssertEqual(StreamPlan.snapFrameRate(10), 7)
    XCTAssertEqual(StreamPlan.snapFrameRate(60), 30)
    XCTAssertEqual(StreamPlan.snapFrameRate(1), 2)
  }

  // MARK: DAT error triage

  func testCapabilityDeniedIsRecognisedUnderAnyName() {
    XCTAssertEqual(DatErrorTriage.classify("DeviceSessionError.CAPABILITY_DENIED"), .capabilityDenied)
    XCTAssertEqual(DatErrorTriage.classify("capabilityDenied"), .capabilityDenied)
    XCTAssertEqual(DatErrorTriage.classify("The device denied the requested capability"), .capabilityDenied)
  }

  func testOtherErrorKinds() {
    XCTAssertEqual(DatErrorTriage.classify("noEligibleDevice"), .noDevice)
    XCTAssertEqual(DatErrorTriage.classify("datAppOnTheGlassesUpdateRequired"), .updateRequired)
    XCTAssertEqual(DatErrorTriage.classify("thermalCritical"), .thermalOrPower)
    XCTAssertEqual(DatErrorTriage.classify("timeout"), .other)
  }
}
