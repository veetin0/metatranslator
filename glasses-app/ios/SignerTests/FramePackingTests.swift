import XCTest

@testable import Signer

/// CONTRACTS section 3: `[4-byte big-endian uint32 header length][UTF-8 JSON header][JPEG]`.
final class FramePackingTests: XCTestCase {
  private let jpeg = Data([0xFF, 0xD8, 0xFF, 0xD9])
  private let header = FrameHeader(seq: 123, tsMs: 1_731_520_000_123, w: 504, h: 896, source: .glasses, rot: 0)

  func testHeaderLengthPrefixIsBigEndian() {
    let msg = FramePacker.pack(header: header, jpeg: jpeg)
    let json = header.jsonData
    XCTAssertEqual(json.count, 76)  // 0x4C
    XCTAssertEqual(Array(msg.prefix(4)), [0x00, 0x00, 0x00, 0x4C])
    XCTAssertEqual(msg.count, 4 + json.count + jpeg.count)
  }

  func testHeaderJSONFieldsAndKeyOrder() throws {
    let text = String(decoding: header.jsonData, as: UTF8.self)
    XCTAssertEqual(
      text, #"{"seq":123,"ts_ms":1731520000123,"w":504,"h":896,"source":"glasses","rot":0}"#)
    let obj = try XCTUnwrap(JSONSerialization.jsonObject(with: header.jsonData) as? [String: Any])
    XCTAssertEqual(Set(obj.keys), ["seq", "ts_ms", "w", "h", "source", "rot"])
    XCTAssertEqual(obj["source"] as? String, "glasses")
    XCTAssertEqual(obj["rot"] as? Int, 0)
  }

  /// Bytes produced by `signer_core.contracts.pack_frame` for the same header and JPEG stub.
  func testMatchesPythonPackFrameByteForByte() {
    let expectedHex =
      "0000004c7b22736571223a3132332c2274735f6d73223a313733313532303030303132332c2277223a3530342c2268223a3839362c22736f75726365223a22676c6173736573222c22726f74223a307dffd8ffd9"
    let hex = FramePacker.pack(header: header, jpeg: jpeg).map { String(format: "%02x", $0) }.joined()
    XCTAssertEqual(hex, expectedHex)
  }

  func testJPEGBytesFollowHeaderUnchanged() {
    let msg = FramePacker.pack(header: header, jpeg: jpeg)
    XCTAssertEqual(Data(msg.suffix(jpeg.count)), jpeg)
  }

  func testUnpackRoundTrip() throws {
    let big = Data((0..<5000).map { UInt8($0 & 0xFF) })
    let msg = FramePacker.pack(header: header, jpeg: big)
    let out = try XCTUnwrap(FramePacker.unpack(msg))
    XCTAssertEqual(out.header, header)
    XCTAssertEqual(out.jpeg, big)
  }

  func testUnpackRejectsTruncatedMessages() {
    XCTAssertNil(FramePacker.unpack(Data([0, 0])))
    XCTAssertNil(FramePacker.unpack(Data([0, 0, 0, 200, 1, 2, 3])))
  }

  func testSourceValuesMatchContract() {
    for (source, word) in [(FrameSource.glasses, "glasses"), (.webcam, "webcam"), (.mock, "mock")] {
      let h = FrameHeader(seq: 0, tsMs: 0, w: 1, h: 1, source: source, rot: 90)
      XCTAssertTrue(String(decoding: h.jsonData, as: UTF8.self).contains("\"source\":\"\(word)\",\"rot\":90"))
    }
  }

  func testJPEGQualityIsSeventyPercent() {
    XCTAssertEqual(FramePacker.jpegQuality, 0.7, accuracy: 1e-9)
  }

  func testSequencerNumbersFramesFromZeroAndResets() {
    var s = FrameSequencer(source: .glasses)
    XCTAssertEqual(s.header(nowMs: 10, w: 504, h: 896).seq, 0)
    XCTAssertEqual(s.header(nowMs: 20, w: 504, h: 896).seq, 1)
    let third = s.header(nowMs: 30, w: 504, h: 896)
    XCTAssertEqual(third.seq, 2)
    XCTAssertEqual(third.tsMs, 30)
    XCTAssertEqual(third.source, .glasses)
    s.reset()
    XCTAssertEqual(s.header(nowMs: 40, w: 1, h: 1).seq, 0)
  }

  func testMockSourceIsLabelledMock() {
    var s = FrameSequencer(source: .mock)
    let h = s.header(nowMs: 1, w: 504, h: 896)
    XCTAssertEqual(h.source, .mock)
    XCTAssertTrue(String(decoding: h.jsonData, as: UTF8.self).contains("\"source\":\"mock\""))
  }
}
