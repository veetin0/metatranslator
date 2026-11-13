import XCTest

@testable import Signer

/// App to core state message (CONTRACTS section 4 app state relay). `AppFlags.sendStateToCore` is ON.
final class StateMessageTests: XCTestCase {
  private func json(_ s: String) throws -> [String: Any] {
    try XCTUnwrap(JSONSerialization.jsonObject(with: Data(s.utf8)) as? [String: Any])
  }

  func testFlagIsOnByDefault() {
    XCTAssertTrue(AppFlags.sendStateToCore)
    var reporter = StateReporter()
    XCTAssertEqual(reporter.message(for: .glassesOff, nowMs: 1)?.state, .glassesOff)
  }

  func testNothingIsSentWithTheFlagOff() {
    var reporter = StateReporter(enabled: false)
    XCTAssertNil(reporter.message(for: .glassesOff, nowMs: 1))
  }

  func testEncodingOfEachReportableState() throws {
    let cases: [(AppState, String)] = [
      (.on, "on"), (.glassesOff, "glasses_off"), (.permissionDenied, "permission_denied"),
    ]
    for (state, wire) in cases {
      let m = try XCTUnwrap(StateMessage(appState: state, nowMs: 1_731_520_000_123))
      let obj = try json(m.jsonString)
      XCTAssertEqual(obj["type"] as? String, "state")
      XCTAssertEqual(obj["state"] as? String, wire)
      XCTAssertEqual(obj["link"] as? String, "ok")
      XCTAssertEqual(obj["from"] as? String, "app")
      XCTAssertEqual((obj["ts"] as? NSNumber)?.int64Value, 1_731_520_000_123)
      XCTAssertEqual(obj.count, 5, "exactly type, state, link, ts, from")
    }
  }

  func testUnreportableStatesProduceNoMessage() {
    for s in [AppState.off, .connecting, .paused, .coreDown] {
      XCTAssertNil(StateMessage(appState: s, nowMs: 1), "\(s)")
    }
  }

  func testClientMessageCarriesTheStateJson() throws {
    let m = try XCTUnwrap(StateMessage(appState: .glassesOff, nowMs: 5))
    XCTAssertEqual(ClientMessage.appState(m).jsonString, m.jsonString)
  }

  func testMessageDecodesBack() throws {
    let m = try XCTUnwrap(StateMessage(appState: .permissionDenied, nowMs: 42))
    let back = try JSONDecoder().decode(StateMessage.self, from: Data(m.jsonString.utf8))
    XCTAssertEqual(back, m)
  }

  func testReporterSendsOnlyOnChangeWhenEnabled() throws {
    var reporter = StateReporter(enabled: true)
    XCTAssertEqual(reporter.message(for: .glassesOff, nowMs: 1)?.state, .glassesOff)
    XCTAssertNil(reporter.message(for: .glassesOff, nowMs: 2), "unchanged")
    XCTAssertEqual(reporter.message(for: .on, nowMs: 3)?.state, .on)
    XCTAssertNil(reporter.message(for: .coreDown, nowMs: 4), "core_down is never sent")
    XCTAssertEqual(reporter.message(for: .on, nowMs: 5)?.state, .on, "back to on after core_down")
  }

  func testReporterResendsAfterReconnect() {
    var reporter = StateReporter(enabled: true)
    XCTAssertNotNil(reporter.message(for: .permissionDenied, nowMs: 1))
    reporter.reset()
    XCTAssertNotNil(reporter.message(for: .permissionDenied, nowMs: 2))
  }
}
