import Foundation
import MWDATCore
import MWDATMockDevice
import UIKit

/// Mock Device Kit: a simulated Meta Ray-Ban Display so the whole path runs without glasses
/// (BirdSpotter's DatMockDeviceRepository). Real DAT calls:
///   MockDeviceKit.shared.enable(config: MockDeviceKitConfig(initiallyRegistered:initialPermissionsGranted:))
///   kit.pairGlasses(model: .metaRayBanDisplay) -> MockGlasses; glasses.powerOn()/unfold()/don()
///   glasses.services.camera.setCameraFeed(fileURL:) / setCameraFeed(cameraFacing:)
///   glasses.services.display.createPreviewView()   (in-app preview of the Display session)
///   kit.startTestServer(port:)                     (simulator only: Chrome display simulator)
///
/// Order matters: `Wearables.configure()` must have run before `enable`, or the kit
/// configures DAT itself and a later configure crashes (BirdSpotterApp.swift).
/// Pairing without a camera feed is a fatal crash in the kit, so a feed is set at once.
final class MockDeviceRepository: @unchecked Sendable {
  enum Feed: String, CaseIterable { case clip, phoneBackCamera }

  static let defaultsKey = "signer.mockEnabled"
  static let clipName = "mock-feed"  // Signer/Resources/mock-feed.mov: 504x896 hvc1 test pattern
  static let chromePreviewPort: UInt16 = 9000

  private let kit: any MockDeviceKitInterface
  private let lock = NSLock()
  private var glasses: (any MockGlasses)?
  private let log = SpikeLog.shared

  init(kit: any MockDeviceKitInterface = MockDeviceKit.shared) {
    self.kit = kit
  }

  var isEnabled: Bool { kit.isEnabled }
  var isPaired: Bool { lock.withLock { glasses != nil } }

  /// Enables the kit and pairs one simulated Ray-Ban Display, powered on, unfolded, worn.
  func enableAndPair(feed: Feed = .clip) {
    if !kit.isEnabled {
      kit.enable(config: MockDeviceKitConfig(initiallyRegistered: true, initialPermissionsGranted: true))
    }
    guard !isPaired else { return }
    do {
      let g = try kit.pairGlasses(model: .metaRayBanDisplay)
      lock.withLock { glasses = g }
      g.powerOn()
      g.unfold()
      g.don()
      setFeed(feed)
      log.add("mock: paired metaRayBanDisplay \(g.deviceIdentifier)")
    } catch {
      log.add("mock: pairGlasses failed: \(DatErrorTriage.describe(error))")
    }
  }

  func disable() {
    lock.withLock { glasses = nil }
    kit.disable()
    log.add("mock: disabled")
  }

  func setFeed(_ feed: Feed) {
    guard let g = lock.withLock({ glasses }) else { return }
    switch feed {
    case .clip:
      if let url = Bundle.main.url(forResource: Self.clipName, withExtension: "mov") {
        g.services.camera.setCameraFeed(fileURL: url)
        log.add("mock: camera feed = bundled clip")
      } else {
        log.add("mock: bundled clip missing; falling back to the phone back camera")
        g.services.camera.setCameraFeed(cameraFacing: .back)
      }
    case .phoneBackCamera:
      g.services.camera.setCameraFeed(cameraFacing: .back)
      log.add("mock: camera feed = phone back camera")
    }
  }

  /// In-app view of what the simulated display shows (rehearses check (b) without glasses).
  @MainActor
  func displayPreviewView() -> UIView? {
    lock.withLock { glasses }?.services.display.createPreviewView()
  }

  /// Serves the display to the Chrome "Meta Ray-Ban Display Simulator" at http://127.0.0.1:9000/
  /// (iOS Simulator only, per the docs).
  func startChromePreviewServer() async {
    do {
      let port = try await kit.startTestServer(port: Self.chromePreviewPort)
      log.add("mock: Chrome display preview at http://127.0.0.1:\(port)/")
    } catch {
      log.add("mock: preview server failed: \(DatErrorTriage.describe(error))")
    }
  }

  // Device state, for the (d) and (f) side checks without hardware.
  func don() { lock.withLock { glasses }?.don() }
  func doff() { lock.withLock { glasses }?.doff() }
  func fold() { lock.withLock { glasses }?.fold() }
  func unfold() { lock.withLock { glasses }?.unfold() }
  func setThermal(_ level: ThermalLevel) { lock.withLock { glasses }?.setThermalLevel(level) }
}
