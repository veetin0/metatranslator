import XCTest

@testable import Signer

/// Tier to colour mapping (DESIGN.md Lens palette), caption wrapping and the speech policy.
final class LensTests: XCTestCase {
  // MARK: tier -> colour

  func testTierToToneMapping() {
    XCTAssertEqual(LensTone(tier: .confirmed), .confirmed)
    XCTAssertEqual(LensTone(tier: .unsure), .unsure)
    XCTAssertEqual(LensTone(tier: .none), .dim)
  }

  func testToneHexMatchesDesignSystem() {
    XCTAssertEqual(LensTone.confirmed.hex, "#FFFFFF")  // --lens-text
    XCTAssertEqual(LensTone.unsure.hex, "#FFB020")  // --lens-unsure
    XCTAssertEqual(LensTone.dim.hex, "#9AA4B2")  // --lens-dim
  }

  /// DAT `Text` has only primary/secondary, so amber cannot be drawn on the glasses. The
  /// tier then rides on the slot and the "?" prefix.
  func testDatSlotsAndUnsurePrefix() {
    XCTAssertEqual(LensTone.confirmed.datSlot, .primary)
    XCTAssertEqual(LensTone.unsure.datSlot, .secondary)
    XCTAssertEqual(LensTone.dim.datSlot, .secondary)
    XCTAssertEqual(LensTone.unsure.textPrefix, "? ")
    XCTAssertEqual(LensTone.confirmed.textPrefix, "")
    XCTAssertEqual(LensTone.dim.textPrefix, "")
  }

  // MARK: cards

  private func caption(_ tier: CaptionTier, text: String, speak: Bool, id: String = "c1") -> CaptionEvent {
    CaptionEvent(
      id: id, text: text, gloss: [], tier: tier, confidence: 0.9, alternatives: [], question: false,
      mode: "template", speak: speak, ts: 1)
  }

  func testConfirmedCaptionCard() {
    let card = LensCard.caption(caption(.confirmed, text: "Hello there", speak: true), stats: StatsEvent(confirmed: 17, total: 19))
    XCTAssertEqual(card.lines, ["Hello there"])
    XCTAssertEqual(card.tone, .confirmed)
    XCTAssertEqual(card.stateLine, "Signer ON")
    XCTAssertEqual(card.footer, "17/19 confirmed")
  }

  func testUnsureCaptionCardGetsQuestionMark() {
    let card = LensCard.caption(caption(.unsure, text: "Where is the book?", speak: false))
    XCTAssertEqual(card.lines, ["? Where is the book?"])
    XCTAssertEqual(card.tone, .unsure)
    XCTAssertNil(card.footer)
  }

  func testNoneTierCardIsDim() {
    let card = LensCard.caption(caption(.none, text: "Didn't catch that", speak: false))
    XCTAssertEqual(card.tone, .dim)
    XCTAssertEqual(card.lines, ["Didn't catch that"])
  }

  func testStateCardsCarryTheStateWord() {
    XCTAssertEqual(LensCard.state(.coreDown).stateLine, "Core down")
    XCTAssertEqual(LensCard.state(.permissionDenied).stateLine, "Permission denied")
    XCTAssertEqual(LensCard.state(.glassesOff).stateLine, "Glasses off")
    XCTAssertTrue(LensCard.state(.paused).lines.isEmpty)
  }

  func testHelloCard() {
    XCTAssertEqual(LensCard.hello.lines, ["Hello"])
    XCTAssertEqual(LensCard.hello.tone, .confirmed)
  }

  // MARK: wrapping (max 2 lines x ~24 chars, oldest line drops)

  func testShortTextIsOneLine() {
    XCTAssertEqual(CaptionWrapper.lines("Hello"), ["Hello"])
  }

  func testWrapsAtWordBoundaries() {
    XCTAssertEqual(
      CaptionWrapper.lines("Hello, can I ask a question?"), ["Hello, can I ask a", "question?"])
  }

  func testNeverMoreThanTwoLinesAndOldestDrops() {
    let lines = CaptionWrapper.lines(
      "one two three four five six seven eight nine ten eleven twelve thirteen fourteen")
    XCTAssertEqual(lines.count, 2)
    XCTAssertTrue(lines.allSatisfy { $0.count <= CaptionWrapper.maxCharsPerLine })
    // Greedy lines are "one two three four five", "six seven eight nine ten",
    // "eleven twelve thirteen", "fourteen": only the last two are kept.
    XCTAssertEqual(lines, ["eleven twelve thirteen", "fourteen"])
  }

  func testOverlongWordIsHardSplit() {
    let lines = CaptionWrapper.lines(String(repeating: "x", count: 30))
    XCTAssertEqual(lines, [String(repeating: "x", count: 24), String(repeating: "x", count: 6)])
  }

  func testEmptyTextHasNoLines() {
    XCTAssertTrue(CaptionWrapper.lines("   ").isEmpty)
  }

  // MARK: speech policy (only speak:true, once per id)

  func testOnlySpeakTrueIsSpoken() {
    var p = SpeechPolicy()
    XCTAssertTrue(p.shouldSpeak(caption(.confirmed, text: "Hi", speak: true, id: "c1")))
    XCTAssertFalse(p.shouldSpeak(caption(.unsure, text: "Maybe", speak: false, id: "c2")))
    XCTAssertFalse(p.shouldSpeak(caption(.none, text: "Didn't catch that", speak: false, id: "c3")))
  }

  func testSameCaptionIsNotSpokenTwice() {
    var p = SpeechPolicy()
    let c = caption(.confirmed, text: "Hi", speak: true, id: "c1")
    XCTAssertTrue(p.shouldSpeak(c))
    XCTAssertFalse(p.shouldSpeak(c))
  }

  func testEmptyTextIsNeverSpoken() {
    var p = SpeechPolicy()
    XCTAssertFalse(p.shouldSpeak(caption(.confirmed, text: "", speak: true)))
  }
}
