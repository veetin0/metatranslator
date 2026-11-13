import Foundation

/// Phase of the glasses camera stream, mirrored from DAT's `StreamState` so the display
/// gate can be unit-tested without DAT.
enum StreamPhase: Equatable {
  case stopped
  case waitingForDevice
  case starting
  case streaming
  case paused
  case stopping
}

/// The display only sends while the stream is `.streaming` (CONTRACTS section 7).
enum DisplayGate {
  static func mayDraw(streamPhase: StreamPhase, displayStarted: Bool) -> Bool {
    streamPhase == .streaming && displayStarted
  }
}

/// Camera stream settings for check (a). DAT's valid frame rates are 2, 7, 15, 24, 30
/// (docs: develop/dat/streaming). BirdSpotter proves only low/7; M0 has to prove medium.
struct StreamPlan: Equatable {
  enum Resolution: String, CaseIterable { case high, medium, low }
  enum Codec: String, CaseIterable { case raw, hvc1 }

  var resolution: Resolution
  var frameRate: UInt
  var codec: Codec

  /// Default for the spike: medium 504x896 at 15 fps, raw frames (`VideoFrame.makeUIImage()`
  /// works on raw directly; raw pauses when the app is backgrounded, which is fine here).
  static let primary = StreamPlan(resolution: .medium, frameRate: 15, codec: .raw)
  /// Fallback when the Bluetooth link cannot carry the primary: low 360x640 at 7 fps.
  static let fallback = StreamPlan(resolution: .low, frameRate: 7, codec: .raw)

  static let validFrameRates: [UInt] = [2, 7, 15, 24, 30]

  /// Frame size DAT documents per resolution (portrait 9:16).
  var expectedSize: (w: Int, h: Int) {
    switch resolution {
    case .high: return (720, 1280)
    case .medium: return (504, 896)
    case .low: return (360, 640)
    }
  }

  var label: String {
    let s = expectedSize
    return "\(resolution.rawValue) \(s.w)x\(s.h) @\(frameRate) fps \(codec.rawValue)"
  }

  /// Nearest valid DAT frame rate at or below the request (never above).
  static func snapFrameRate(_ requested: UInt) -> UInt {
    validFrameRates.last(where: { $0 <= requested }) ?? validFrameRates[0]
  }
}
