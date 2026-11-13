import XCTest

@testable import Signer

/// D3 states (permission_denied, glasses_off, core_down): every trigger maps to the right
/// AppState and the right lens state line + next step; core_down needs a socket drop longer
/// than 2 s on an injected clock; the readout footer comes from `stats` events.
final class AppStateTests: XCTestCase {
  // MARK: trigger -> AppState

  func testCameraPermissionDeniedGivesPermissionDenied() {
    var s = AppSignals()
    s.beginStart()
    s.cameraPermission = .denied
    s.end(byDevice: false)  // the failed start ends the run; the fault stays
    XCTAssertEqual(AppStateResolver.resolve(s), .permissionDenied)
  }

  func testDatCapabilityDeniedErrorGivesPermissionDenied() {
    var s = AppSignals()
    XCTAssertEqual(s.apply(datError: "capabilityDenied (CAPABILITY_DENIED)"), .permissionDenied)
    XCTAssertEqual(s.cameraPermission, .denied)
    XCTAssertEqual(AppStateResolver.resolve(s), .permissionDenied)
  }

  func testDatPermissionDeniedTextGivesPermissionDenied() {
    var s = AppSignals()
    XCTAssertEqual(s.apply(datError: "camera permission request failed: permission denied"), .permissionDenied)
  }

  func testNoEligibleDeviceGivesGlassesOff() {
    var s = AppSignals()
    s.beginStart()
    XCTAssertEqual(s.apply(datError: "noEligibleDevice"), .glassesOff)
    XCTAssertEqual(AppStateResolver.resolve(s), .glassesOff)
  }

  func testNoDeviceListWhileRunningGivesGlassesOff() {
    var s = AppSignals()
    s.beginStart()
    s.apply(deviceCount: 0)
    XCTAssertEqual(AppStateResolver.resolve(s), .glassesOff)
    s.apply(deviceCount: 1)
    XCTAssertEqual(AppStateResolver.resolve(s), .connecting, "glasses back: fault cleared")
  }

  func testNoDeviceListWhileIdleIsNotAFault() {
    var s = AppSignals()
    s.apply(deviceCount: 0)
    XCTAssertEqual(AppStateResolver.resolve(s), .off)
  }

  func testDeviceEndingTheSessionGivesGlassesOff() {
    var s = AppSignals()
    s.beginStart()
    s.base = .on
    s.end(byDevice: true)
    XCTAssertEqual(AppStateResolver.resolve(s), .glassesOff)
  }

  func testStoppingByUsIsJustOff() {
    var s = AppSignals()
    s.beginStart()
    s.base = .on
    s.end(byDevice: false)
    XCTAssertEqual(AppStateResolver.resolve(s), .off)
  }

  func testUnrelatedDatErrorsChangeNothing() {
    var s = AppSignals()
    XCTAssertNil(s.apply(datError: "thermalHot"))
    XCTAssertNil(s.apply(datError: "something odd"))
    XCTAssertEqual(AppStateResolver.resolve(s), .off)
  }

  func testNextStartForgetsLastFaults() {
    var s = AppSignals()
    s.cameraPermission = .denied
    s.glassesOff = true
    s.beginStart()
    XCTAssertEqual(AppStateResolver.resolve(s), .connecting)
  }

  // MARK: precedence

  func testCoreOnDoesNotWipeALocalFault() {
    var s = AppSignals()
    s.beginStart()
    s.glassesOff = true
    s.base = AppState(lens: .on)  // the core says ON
    XCTAssertEqual(AppStateResolver.resolve(s), .glassesOff)
  }

  func testPrecedenceOrder() {
    var s = AppSignals()
    s.beginStart()
    s.base = .on
    s.coreDown = true
    XCTAssertEqual(AppStateResolver.resolve(s), .coreDown)
    s.glassesOff = true
    XCTAssertEqual(AppStateResolver.resolve(s), .glassesOff)
    s.cameraPermission = .denied
    XCTAssertEqual(AppStateResolver.resolve(s), .permissionDenied)
    s.debugOverride = .coreDown
    XCTAssertEqual(AppStateResolver.resolve(s), .coreDown, "debug override wins")
    s.debugOverride = nil
    XCTAssertEqual(AppStateResolver.resolve(s), .permissionDenied)
  }

  func testCoreDownIgnoredWhileIdle() {
    var s = AppSignals()
    s.coreDown = true  // sockets are closed on purpose when idle
    XCTAssertEqual(AppStateResolver.resolve(s), .off)
  }

  func testEachDebugTriggerGivesItsState() {
    for state in [AppState.permissionDenied, .glassesOff, .coreDown] {
      var s = AppSignals()
      s.debugOverride = state
      XCTAssertEqual(AppStateResolver.resolve(s), state)
    }
  }

  // MARK: lens state line + next step

  func testStateLineAndNextStepPerFault() {
    XCTAssertEqual(AppState.permissionDenied.label, "Permission denied")
    XCTAssertEqual(AppState.glassesOff.label, "Glasses off")
    XCTAssertEqual(AppState.coreDown.label, "Core down")
    XCTAssertEqual(AppState.permissionDenied.rawValue, "permission_denied")
    XCTAssertEqual(AppState.glassesOff.rawValue, "glasses_off")
    XCTAssertEqual(AppState.coreDown.rawValue, "core_down")
    for fault in [AppState.permissionDenied, .glassesOff, .coreDown] {
      XCTAssertTrue(fault.isFault)
      XCTAssertNotNil(fault.nextStep)
    }
    for ok in [AppState.off, .connecting, .on, .paused] {
      XCTAssertFalse(ok.isFault)
      XCTAssertNil(ok.nextStep)
    }
  }

  func testEveryFaultCardShowsStateLineAndWholeNextStep() throws {
    for fault in [AppState.permissionDenied, .glassesOff, .coreDown] {
      let card = LensCard.appState(fault)
      XCTAssertEqual(card.stateLine, fault.label)
      let step = try XCTUnwrap(fault.nextStep)
      // Nothing dropped by the 2 x 24 wrapping: the whole step is on the card.
      XCTAssertEqual(card.lines.joined(separator: " "), step, "\(fault) next step fits the lens")
      XCTAssertLessThanOrEqual(card.lines.count, CaptionWrapper.maxLines)
      XCTAssertTrue(card.lines.allSatisfy { $0.count <= CaptionWrapper.maxCharsPerLine })
      XCTAssertEqual(card.tone, .dim)
    }
  }

  func testNonFaultCardHasNoNextStepLines() {
    XCTAssertEqual(LensCard.appState(.on), LensCard.state(.on))
  }

  func testLensStateRoundTrip() {
    for s in AppState.allCases { XCTAssertEqual(AppState(lens: s.lensState), s) }
  }

  func testTriageMapsToAppState() {
    XCTAssertEqual(AppState.fromDatError("CAPABILITY_DENIED"), .permissionDenied)
    XCTAssertEqual(AppState.fromDatError("noEligibleDevice"), .glassesOff)
    XCTAssertNil(AppState.fromDatError("updateRequired"))
  }

  // MARK: core_down after > 2 s (injected clock)

  func testCoreDownOnlyAfterMoreThanTwoSeconds() {
    var m = CoreLinkMonitor()
    XCTAssertFalse(m.isCoreDown(now: 100), "never dropped")
    m.socketDown(at: 100)
    XCTAssertFalse(m.isCoreDown(now: 100.0))
    XCTAssertFalse(m.isCoreDown(now: 101.9))
    XCTAssertFalse(m.isCoreDown(now: 102.0), "exactly 2 s is not more than 2 s")
    XCTAssertTrue(m.isCoreDown(now: 102.1))
  }

  func testReconnectWithinWindowNeverGoesCoreDown() {
    var m = CoreLinkMonitor()
    m.socketDown(at: 10)
    m.socketUp()
    XCTAssertFalse(m.isCoreDown(now: 13))
  }

  func testReconnectAttemptsDoNotRestartTheWindow() {
    var m = CoreLinkMonitor()
    m.socketDown(at: 0)  // dropped
    m.socketDown(at: 1.0)  // CoreClient retries: connecting, fails again
    m.socketDown(at: 2.0)
    XCTAssertTrue(m.isCoreDown(now: 2.1), "counted from the first drop")
  }

  func testCoreRecoversWhenSocketReopens() {
    var m = CoreLinkMonitor()
    m.socketDown(at: 0)
    XCTAssertTrue(m.isCoreDown(now: 5))
    m.socketUp()
    XCTAssertFalse(m.isCoreDown(now: 5.1))
  }

  func testResetForgetsTheDrop() {
    var m = CoreLinkMonitor()
    m.socketDown(at: 0)
    m.reset()
    XCTAssertFalse(m.isCoreDown(now: 50))
  }

  func testSecondsUntilDownSchedulesOneRecheck() throws {
    var m = CoreLinkMonitor()
    XCTAssertNil(m.secondsUntilDown(now: 0))
    m.socketDown(at: 0)
    let wait = try XCTUnwrap(m.secondsUntilDown(now: 0.5))
    XCTAssertEqual(wait, 1.55, accuracy: 0.001)
    XCTAssertTrue(m.isCoreDown(now: 0.5 + wait))
    XCTAssertNil(m.secondsUntilDown(now: 3))
  }

  func testSocketDropToCoreDownStateEndToEnd() {
    var clock: TimeInterval = 1000
    var monitor = CoreLinkMonitor()
    var s = AppSignals()
    func refresh() {
      s.coreDown = monitor.isCoreDown(now: clock)
    }
    s.beginStart()
    s.base = .on
    monitor.socketDown(at: clock)  // the events socket drops
    clock += 1.5
    refresh()
    XCTAssertEqual(AppStateResolver.resolve(s), .on, "1.5 s: still fine, auto-reconnecting")
    clock += 1.0
    refresh()
    XCTAssertEqual(AppStateResolver.resolve(s), .coreDown, "2.5 s: core down")
    monitor.socketUp()  // auto-reconnect worked
    refresh()
    XCTAssertEqual(AppStateResolver.resolve(s), .on)
  }

  // MARK: readout footer

  func testReadoutFooterFromStats() {
    XCTAssertEqual(ReadoutFormat.footer(StatsEvent(confirmed: 17, total: 19)), "17/19 confirmed")
    XCTAssertEqual(ReadoutFormat.footer(StatsEvent(confirmed: 0, total: 0)), "0/0 confirmed")
    XCTAssertNil(ReadoutFormat.footer(nil))
  }

  func testFooterOnEveryCardKind() {
    let stats = StatsEvent(confirmed: 17, total: 19)
    let caption = CaptionEvent(
      id: "c1", text: "Hello", gloss: [], tier: .confirmed, confidence: 0.9, alternatives: [],
      question: false, mode: "template", speak: true, ts: 1)
    XCTAssertEqual(LensCard.caption(caption, stats: stats).footer, "17/19 confirmed")
    XCTAssertEqual(LensCard.state(.on, stats: stats).footer, "17/19 confirmed")
    XCTAssertEqual(LensCard.appState(.coreDown, stats: stats).footer, "17/19 confirmed")
    XCTAssertNil(LensCard.caption(caption).footer)
  }

  func testStatsChangeRedrawsCardInsideThrottleOnce() {
    // New stats change the card, so the throttle sends it (trailing, 500 ms rule), while the
    // same stats again are dropped.
    var t = SendThrottle<LensCard>()
    let a = LensCard.state(.on, stats: StatsEvent(confirmed: 17, total: 19))
    let b = LensCard.state(.on, stats: StatsEvent(confirmed: 18, total: 20))
    XCTAssertEqual(t.offer(a, now: 0), .send(a))
    XCTAssertEqual(t.offer(a, now: 0.1), .drop)
    XCTAssertEqual(t.offer(b, now: 0.2), .wait(until: 0.5))
    XCTAssertEqual(t.poll(now: 0.5), b)
  }
}
