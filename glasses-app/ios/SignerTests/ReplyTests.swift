import XCTest

@testable import Signer

/// `POST /reply {"text","source":"stt"|"typed"}` (CONTRACTS section 2) and the reply box flow.
final class ReplyTests: XCTestCase {
  private let endpoints = CoreEndpoints("ws://172.20.10.2:8000")!

  private func body(_ req: URLRequest) throws -> [String: Any] {
    let data = try XCTUnwrap(req.httpBody)
    return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
  }

  // MARK: request encoding

  func testSttReplyRequestEncoding() throws {
    let reply = try XCTUnwrap(ReplyRequest(text: "Sure, page 12", source: .stt))
    let req = reply.urlRequest(endpoints: endpoints)
    XCTAssertEqual(req.httpMethod, "POST")
    XCTAssertEqual(req.url?.absoluteString, "http://172.20.10.2:8000/reply")
    XCTAssertEqual(req.value(forHTTPHeaderField: "Content-Type"), "application/json")
    let json = try body(req)
    XCTAssertEqual(json["text"] as? String, "Sure, page 12")
    XCTAssertEqual(json["source"] as? String, "stt")
    XCTAssertEqual(json.count, 2, "exactly {text, source}")
  }

  func testTypedReplyRequestEncoding() throws {
    let reply = try XCTUnwrap(ReplyRequest(text: "Yes please", source: .typed))
    let json = try body(reply.urlRequest(endpoints: endpoints))
    XCTAssertEqual(json["text"] as? String, "Yes please")
    XCTAssertEqual(json["source"] as? String, "typed")
  }

  func testReplyUrlFollowsTheCoreBase() throws {
    let tunnel = CoreEndpoints("wss://example.trycloudflare.com")!
    let req = try XCTUnwrap(ReplyRequest(text: "hi", source: .typed)).urlRequest(endpoints: tunnel)
    XCTAssertEqual(req.url?.absoluteString, "https://example.trycloudflare.com/reply")
  }

  func testQuotesAndUnicodeSurviveEncoding() throws {
    let text = "She said \"page 12\" \u{2014} caf\u{00E9}"
    let reply = try XCTUnwrap(ReplyRequest(text: text, source: .typed))
    XCTAssertEqual(try body(reply.urlRequest(endpoints: endpoints))["text"] as? String, text)
  }

  func testEmptyAndWhitespaceRepliesAreRejected() {
    XCTAssertNil(ReplyRequest(text: "", source: .stt))
    XCTAssertNil(ReplyRequest(text: "  \n\t ", source: .typed))
  }

  func testWhitespaceIsNormalisedAndLongTextIsCut() throws {
    XCTAssertEqual(ReplyRequest(text: "  Sure,\n page   12 ", source: .stt)?.text, "Sure, page 12")
    let long = String(repeating: "a", count: 1000)
    XCTAssertEqual(ReplyRequest(text: long, source: .typed)?.text.count, ReplyRequest.maxLength)
  }

  func testClientMessageStateAndReplyStillEncode() throws {
    let json = try XCTUnwrap(
      JSONSerialization.jsonObject(
        with: Data(ClientMessage.reply(text: "ok", source: "stt").jsonString.utf8)) as? [String: Any])
    XCTAssertEqual(json["type"] as? String, "reply")
  }

  // MARK: composer: hold to talk

  func testHoldToTalkProducesSttRequestFromFinalText() throws {
    var c = ReplyComposer()
    c.beginListening()
    XCTAssertEqual(c.phase, .listening)
    c.updatePartial("sure pa")
    XCTAssertEqual(c.partial, "sure pa")
    c.endListening()
    XCTAssertEqual(c.phase, .processing)
    let req = try XCTUnwrap(c.finishListening(finalText: "Sure, page 12"))
    XCTAssertEqual(req, ReplyRequest(text: "Sure, page 12", source: .stt))
    XCTAssertEqual(c.phase, .sending)
    c.sendSucceeded(req)
    XCTAssertEqual(c.phase, .sent("Sure, page 12"))
  }

  func testFinalFallsBackToLastPartial() throws {
    var c = ReplyComposer()
    c.beginListening()
    c.updatePartial("page twelve")
    c.endListening()
    XCTAssertEqual(c.finishListening(finalText: nil)?.text, "page twelve")
  }

  func testNothingHeardSendsNothingAndSaysSo() {
    var c = ReplyComposer()
    c.beginListening()
    c.endListening()
    XCTAssertNil(c.finishListening(finalText: ""))
    guard case .failed(let message) = c.phase else { return XCTFail("expected failed, got \(c.phase)") }
    XCTAssertTrue(message.contains("type"), "points to the typed fallback")
  }

  func testSpeechUnavailableKeepsTypingWorking() {
    var c = ReplyComposer()
    c.beginListening()
    c.speechUnavailable("Speech or microphone access is off.")
    XCTAssertEqual(c.phase, .unavailable("Speech or microphone access is off."))
    c.typed = "Hello"
    XCTAssertTrue(c.canSendTyped)
  }

  func testCannotStartListeningWhileSending() throws {
    var c = ReplyComposer()
    c.typed = "hi"
    _ = try XCTUnwrap(c.submitTyped())
    c.beginListening()
    XCTAssertEqual(c.phase, .sending)
  }

  // MARK: composer: typed fallback

  func testTypedSubmitBuildsTypedRequestAndClearsField() throws {
    var c = ReplyComposer()
    c.typed = "  Yes please "
    XCTAssertTrue(c.canSendTyped)
    let req = try XCTUnwrap(c.submitTyped())
    XCTAssertEqual(req, ReplyRequest(text: "Yes please", source: .typed))
    XCTAssertEqual(c.typed, "")
    XCTAssertEqual(c.phase, .sending)
  }

  func testEmptyTypedFieldCannotBeSent() {
    var c = ReplyComposer()
    XCTAssertFalse(c.canSendTyped)
    XCTAssertNil(c.submitTyped())
    c.typed = "   "
    XCTAssertFalse(c.canSendTyped)
  }

  func testFailedTypedSendGivesTheTextBack() throws {
    var c = ReplyComposer()
    c.typed = "Yes please"
    let req = try XCTUnwrap(c.submitTyped())
    c.sendFailed(req, reason: "core not reachable")
    XCTAssertEqual(c.typed, "Yes please")
    XCTAssertEqual(c.phase, .failed("Not sent: core not reachable"))
  }

  // MARK: flags

  func testSttFlagParsing() {
    XCTAssertTrue(AppFlags.replySTTEnabled(rawFlags: nil), "no flags set on the phone: on")
    XCTAssertTrue(AppFlags.replySTTEnabled(rawFlags: ""))
    XCTAssertTrue(AppFlags.replySTTEnabled(rawFlags: "teach, Reply_STT"))
    XCTAssertFalse(AppFlags.replySTTEnabled(rawFlags: "teach,llm"))
  }

  func testFlagsComeFromLaunchArgumentThenEnvironment() {
    XCTAssertEqual(AppFlags.current(arguments: ["x", "--flags", "teach"], environment: ["SIGNER_FLAGS": "llm"]), "teach")
    XCTAssertEqual(AppFlags.current(arguments: ["x"], environment: ["SIGNER_FLAGS": "llm"]), "llm")
    XCTAssertNil(AppFlags.current(arguments: ["x"], environment: [:]))
  }
}
