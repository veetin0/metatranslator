import XCTest

@testable import Signer

/// CONTRACTS section 4, against `contracts/events.example.jsonl` (copied into
/// SignerTests/Resources: it is the contract's one example of every WS event).
final class EventDecodingTests: XCTestCase {
  private func exampleLines() throws -> [String] {
    let url = try XCTUnwrap(
      Bundle(for: Self.self).url(forResource: "events.example", withExtension: "jsonl"),
      "events.example.jsonl missing from the test bundle")
    let text = try String(contentsOf: url, encoding: .utf8)
    return text.split(whereSeparator: \.isNewline).map(String.init).filter { !$0.isEmpty }
  }

  func testEveryExampleLineDecodesToAKnownEvent() throws {
    let lines = try exampleLines()
    XCTAssertEqual(lines.count, 14)
    for line in lines {
      let event = try CoreEvent.decode(line: line)
      if case .unknown(let type) = event {
        XCTFail("unknown event type \(type) in: \(line)")
      }
    }
  }

  func testExampleSequenceOfTypes() throws {
    let kinds = try exampleLines().map { line -> String in
      switch try CoreEvent.decode(line: line) {
      case .state: return "state"
      case .partial: return "partial"
      case .caption: return "caption"
      case .retract: return "retract"
      case .reply: return "reply"
      case .stats: return "stats"
      case .ack: return "ack"
      case .unknown: return "unknown"
      }
    }
    XCTAssertEqual(
      kinds,
      ["state", "state", "partial", "caption", "caption", "caption", "retract", "reply", "stats",
       "state", "state", "state", "state", "state"])
  }

  func testConfirmedCaptionFields() throws {
    guard case .caption(let c) = try CoreEvent.decode(line: try exampleLines()[3]) else {
      return XCTFail("not a caption")
    }
    XCTAssertEqual(c.id, "c1")
    XCTAssertEqual(c.text, "Hello, can I ask a question?")
    XCTAssertEqual(c.gloss, ["HELLO", "QUESTION"])
    XCTAssertEqual(c.tier, .confirmed)
    XCTAssertEqual(c.confidence, 0.86, accuracy: 1e-9)
    XCTAssertTrue(c.alternatives.isEmpty)
    XCTAssertTrue(c.question)
    XCTAssertEqual(c.mode, "template")
    XCTAssertTrue(c.speak)
    XCTAssertEqual(c.ts, 1_731_520_003_000)
  }

  func testUnsureCaptionCarriesAlternativesAndIsNotSpoken() throws {
    guard case .caption(let c) = try CoreEvent.decode(line: try exampleLines()[4]) else {
      return XCTFail("not a caption")
    }
    XCTAssertEqual(c.tier, .unsure)
    XCTAssertFalse(c.speak)
    XCTAssertEqual(c.alternatives.count, 1)
    XCTAssertEqual(c.alternatives[0].text, "Where is the paper?")
    XCTAssertEqual(c.alternatives[0].gloss, ["WHERE", "PAPER"])
    XCTAssertEqual(c.alternatives[0].confidence, 0.41, accuracy: 1e-9)
  }

  func testNoneTierCaption() throws {
    guard case .caption(let c) = try CoreEvent.decode(line: try exampleLines()[5]) else {
      return XCTFail("not a caption")
    }
    XCTAssertEqual(c.tier, .none)
    XCTAssertEqual(c.text, "Didn't catch that")
    XCTAssertTrue(c.gloss.isEmpty)
    XCTAssertFalse(c.speak)
  }

  func testStateEventsCoverEveryLensState() throws {
    var seen: [LensState] = []
    var slow = false
    for line in try exampleLines() {
      if case .state(let s) = try CoreEvent.decode(line: line) {
        seen.append(s.state)
        if s.link == .slow { slow = true }
      }
    }
    XCTAssertEqual(
      Set(seen), [.connecting, .on, .paused, .glassesOff, .permissionDenied, .off])
    XCTAssertTrue(slow, "the example has a link:slow state event")
  }

  func testRetractReplyStatsPartial() throws {
    let lines = try exampleLines()
    XCTAssertEqual(try CoreEvent.decode(line: lines[6]), .retract(id: "c2"))
    guard case .reply(let r) = try CoreEvent.decode(line: lines[7]) else { return XCTFail("reply") }
    XCTAssertEqual(r.text, "Sure, it's on page 12")
    XCTAssertEqual(r.source, "stt")
    XCTAssertEqual(try CoreEvent.decode(line: lines[8]), .stats(StatsEvent(confirmed: 17, total: 19)))
    guard case .partial(let p) = try CoreEvent.decode(line: lines[2]) else { return XCTFail("partial") }
    XCTAssertEqual(p.gloss, "HELLO")
    XCTAssertEqual(p.confidence, 0.62, accuracy: 1e-9)
  }

  func testAckOnTheFramesSocket() throws {
    XCTAssertEqual(try CoreEvent.decode(line: #"{"type":"ack","seq":30}"#), .ack(seq: 30))
  }

  func testUnknownTypeIsKeptNotFatal() throws {
    XCTAssertEqual(
      try CoreEvent.decode(line: #"{"type":"future_thing","x":1}"#), .unknown(type: "future_thing"))
  }

  func testMalformedInputThrowsTypedErrors() {
    XCTAssertThrowsError(try CoreEvent.decode(line: "not json")) {
      XCTAssertEqual($0 as? CoreEvent.DecodeError, .notJSONObject)
    }
    XCTAssertThrowsError(try CoreEvent.decode(line: #"{"id":"x"}"#)) {
      XCTAssertEqual($0 as? CoreEvent.DecodeError, .missingType)
    }
    XCTAssertThrowsError(try CoreEvent.decode(line: #"{"type":"retract"}"#))
    XCTAssertThrowsError(try CoreEvent.decode(line: #"{"type":"caption","id":"c9"}"#))
  }

  func testClientMessagesEncode() throws {
    XCTAssertEqual(ClientMessage.hello(.app).jsonString, #"{"type":"hello","client":"app"}"#)
    let fb = try XCTUnwrap(
      JSONSerialization.jsonObject(
        with: Data(ClientMessage.feedback(captionId: "c42", verdict: .veto).jsonString.utf8))
        as? [String: String])
    XCTAssertEqual(fb, ["type": "feedback", "caption_id": "c42", "verdict": "veto"])
    let reply = try XCTUnwrap(
      JSONSerialization.jsonObject(
        with: Data(ClientMessage.reply(text: "Sure, \"page\" 12", source: "typed").jsonString.utf8))
        as? [String: String])
    XCTAssertEqual(reply["text"], "Sure, \"page\" 12")
    XCTAssertEqual(reply["source"], "typed")
  }
}
