import Foundation
import MWDATCamera
import MWDATCore
import UIKit

/// The glasses camera stream. Real DAT calls (docs: develop/dat/streaming; samples/CameraAccess):
///   session.addCamera(config: StreamConfiguration(videoCodec:resolution:frameRate:)) -> Camera?
///   camera.stream.statePublisher / videoFramePublisher / errorPublisher, camera.stream.start()
///   camera.stop() (cascades to the stream)
///   VideoFrame.makeUIImage() (works on `.raw`; `.hvc1` frames are compressed samples)
/// Frames are turned into JPEG (quality 0.7) right here, on the SDK's callback queue, and
/// handed to `onFrame`. One encode at a time: a frame that arrives while one is encoding
/// is dropped (the core drops anything older than 300 ms anyway).
final class CameraRepository: @unchecked Sendable {
  enum StartError: Error { case cameraNotCreated }

  /// (jpeg, width, height) in pixels.
  var onFrame: (@Sendable (Data, Int, Int) -> Void)?
  var onStreamPhase: (@Sendable (StreamPhase) -> Void)?
  /// Every frame that comes off the glasses, before the encoder gate: this is what check (a)
  /// measures (phone-side fps at the stream's resolution).
  var onFrameArrived: (@Sendable () -> Void)?

  private let lock = NSLock()
  private var camera: Camera?
  private var encoding = false
  private var reportedNilImage = false
  private let tokens = ListenerTokenBag()
  private let log = SpikeLog.shared

  var isAttached: Bool { lock.withLock { camera != nil } }

  func start(on session: DeviceSession, plan: StreamPlan) throws {
    guard !isAttached else { return }
    let config = StreamConfiguration(
      videoCodec: plan.codec.dat,
      resolution: plan.resolution.dat,
      frameRate: StreamPlan.snapFrameRate(plan.frameRate))
    guard let cam = try session.addCamera(config: config) else { throw StartError.cameraNotCreated }
    lock.withLock {
      camera = cam
      encoding = false
      reportedNilImage = false
    }
    log.add("camera: attached, plan \(plan.label)")

    cam.stream.statePublisher.listen { [weak self] state in
      SpikeLog.shared.add("camera stream: \(state)")
      self?.onStreamPhase?(state.phase)
    }.store(in: tokens)

    cam.stream.videoFramePublisher.listen { [weak self] frame in
      self?.handle(frame)
    }.store(in: tokens)

    cam.stream.errorPublisher.listen { error in
      let text = DatErrorTriage.describe(error)
      SpikeLog.shared.add("camera stream error: \(text)")
      if DatErrorTriage.classify(text) == .capabilityDenied {
        SpikeLog.shared.add("!! CAPABILITY_DENIED suspected on the camera: report to Meta immediately")
      }
    }.store(in: tokens)

    cam.stream.start()
  }

  /// Stops the camera (and its stream) but leaves the session up.
  func stop() {
    let cam: Camera? = lock.withLock {
      defer { camera = nil }
      return camera
    }
    cam?.stop()
    tokens.clear()
    onStreamPhase?(.stopped)
  }

  private func handle(_ frame: VideoFrame) {
    onFrameArrived?()
    let proceed: Bool = lock.withLock {
      if encoding { return false }
      encoding = true
      return true
    }
    guard proceed else { return }
    defer { lock.withLock { encoding = false } }

    guard let image = frame.makeUIImage(), let cg = image.cgImage else {
      let first: Bool = lock.withLock {
        defer { reportedNilImage = true }
        return !reportedNilImage
      }
      if first { log.add("camera: makeUIImage() returned nil (codec not decodable?)") }
      return
    }
    guard let jpeg = image.jpegData(compressionQuality: FramePacker.jpegQuality) else { return }
    onFrame?(jpeg, cg.width, cg.height)
  }
}

extension StreamPlan.Codec {
  fileprivate var dat: VideoCodec {
    switch self {
    case .raw: return .raw
    case .hvc1: return .hvc1
    }
  }
}

extension StreamPlan.Resolution {
  fileprivate var dat: StreamingResolution {
    switch self {
    case .high: return .high
    case .medium: return .medium
    case .low: return .low
    }
  }
}

extension StreamState {
  /// DAT `StreamState` to the pure phase used by the display gate.
  var phase: StreamPhase {
    switch self {
    case .stopped: return .stopped
    case .waitingForDevice: return .waitingForDevice
    case .starting: return .starting
    case .streaming: return .streaming
    case .paused: return .paused
    case .stopping: return .stopping
    }
  }
}
