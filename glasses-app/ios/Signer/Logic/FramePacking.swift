import Foundation

/// Where a frame came from (CONTRACTS section 3 `source`).
enum FrameSource: String, Equatable {
  case glasses
  case webcam
  case mock
}

/// Frame header (CONTRACTS section 3): `{"seq":123,"ts_ms":...,"w":504,"h":896,"source":"glasses","rot":0}`.
struct FrameHeader: Equatable {
  var seq: Int
  var tsMs: Int64
  var w: Int
  var h: Int
  var source: FrameSource
  var rot: Int

  init(seq: Int, tsMs: Int64, w: Int, h: Int, source: FrameSource = .glasses, rot: Int = 0) {
    self.seq = seq
    self.tsMs = tsMs
    self.w = w
    self.h = h
    self.source = source
    self.rot = rot
  }

  /// Compact JSON with the contract's key order, the same bytes `pack_frame` in
  /// `core/signer_core/contracts.py` produces (`json.dumps(..., separators=(",", ":"))`).
  /// Built by hand because `JSONEncoder` does not promise key order. `source` is an enum
  /// of plain ASCII words, so no escaping is needed.
  var jsonData: Data {
    let s = "{\"seq\":\(seq),\"ts_ms\":\(tsMs),\"w\":\(w),\"h\":\(h),\"source\":\"\(source.rawValue)\",\"rot\":\(rot)}"
    return Data(s.utf8)
  }
}

/// Binary frame message for `WS /ws/frames` (CONTRACTS section 3):
/// `[4-byte big-endian uint32 header length][UTF-8 JSON header][JPEG bytes]`.
enum FramePacker {
  /// JPEG quality the contract asks for (70).
  static let jpegQuality: Double = 0.7

  static func pack(header: FrameHeader, jpeg: Data) -> Data {
    let json = header.jsonData
    var out = Data(capacity: 4 + json.count + jpeg.count)
    var length = UInt32(json.count).bigEndian
    withUnsafeBytes(of: &length) { out.append(contentsOf: $0) }
    out.append(json)
    out.append(jpeg)
    return out
  }

  /// Inverse of `pack`, used by tests and the self-check. Returns nil on a malformed message.
  static func unpack(_ message: Data) -> (header: FrameHeader, jpeg: Data)? {
    let bytes = [UInt8](message)
    guard bytes.count >= 4 else { return nil }
    let n = bytes[0..<4].reduce(0) { ($0 << 8) | Int($1) }
    guard bytes.count >= 4 + n else { return nil }
    let json = Data(bytes[4..<(4 + n)])
    guard
      let obj = try? JSONSerialization.jsonObject(with: json) as? [String: Any],
      let seq = obj["seq"] as? Int,
      let ts = obj["ts_ms"] as? Int64 ?? (obj["ts_ms"] as? Int).map(Int64.init),
      let w = obj["w"] as? Int,
      let h = obj["h"] as? Int,
      let src = (obj["source"] as? String).flatMap(FrameSource.init(rawValue:)),
      let rot = obj["rot"] as? Int
    else { return nil }
    return (FrameHeader(seq: seq, tsMs: ts, w: w, h: h, source: src, rot: rot), Data(bytes[(4 + n)...]))
  }
}

/// Numbers frames and stamps them. Not thread-safe on its own; callers serialise access.
struct FrameSequencer {
  private(set) var next: Int = 0
  let source: FrameSource

  init(source: FrameSource = .glasses) { self.source = source }

  mutating func header(nowMs: Int64, w: Int, h: Int, rot: Int = 0) -> FrameHeader {
    defer { next += 1 }
    return FrameHeader(seq: next, tsMs: nowMs, w: w, h: h, source: source, rot: rot)
  }

  mutating func reset() { next = 0 }
}
