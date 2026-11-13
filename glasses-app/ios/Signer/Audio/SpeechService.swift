import AVFoundation
import Foundation

/// Phone TTS, heard in the glasses speaker because the glasses are the Bluetooth audio output
/// (check (c)). DAT docs (develop/dat/microphones-and-speakers): use A2DP for output only,
///   AVAudioSession.setCategory(.playback), setActive(true), play with AVSpeechSynthesizer,
///   then verify `currentRoute.outputs` contains `.bluetoothA2DP`.
/// Deliberately not `.playAndRecord` / HFP: that switches the glasses to mono voice quality
/// and is exclusive with A2DP.
/// Speaks only captions with `speak: true` (the core sets it for the `confirmed` tier only).
@MainActor
final class SpeechService: NSObject, AVSpeechSynthesizerDelegate {
  private let synth = AVSpeechSynthesizer()
  private var policy = SpeechPolicy()
  private var currentCaptionId: String?
  private let log = SpikeLog.shared

  override init() {
    super.init()
    synth.delegate = self
  }

  /// Output ports of the current audio route, e.g. "BluetoothA2DPOutput (Ray-Ban Display)".
  var routeDescription: String {
    let outs = AVAudioSession.sharedInstance().currentRoute.outputs
    return outs.isEmpty ? "none" : outs.map { "\($0.portType.rawValue) (\($0.portName))" }.joined(separator: ", ")
  }

  var isOnBluetoothA2DP: Bool {
    AVAudioSession.sharedInstance().currentRoute.outputs.contains { $0.portType == .bluetoothA2DP }
  }

  func configureAudioSession() {
    do {
      let s = AVAudioSession.sharedInstance()
      try s.setCategory(.playback, mode: .spokenAudio, options: [])
      try s.setActive(true, options: .notifyOthersOnDeactivation)
    } catch {
      log.add("speech: audio session failed: \(error.localizedDescription)")
    }
  }

  /// Speaks a caption event if the policy allows (speak == true, once per caption id).
  func speak(caption: CaptionEvent) {
    guard policy.shouldSpeak(caption) else {
      log.add("speech: caption \(caption.id) not spoken (speak=\(caption.speak), tier=\(caption.tier.rawValue))")
      return
    }
    currentCaptionId = caption.id
    say(caption.text)
  }

  /// A veto removes the caption from the lens; stop speaking it too.
  func retract(id: String) {
    guard currentCaptionId == id, synth.isSpeaking else { return }
    synth.stopSpeaking(at: .immediate)
  }

  /// The "Speak test" button: always speaks, then logs which route carried it.
  func speakTest() {
    currentCaptionId = nil
    say("Signer speech test. If you hear this in the glasses, the audio route works.")
  }

  func stop() {
    synth.stopSpeaking(at: .immediate)
  }

  private func say(_ text: String) {
    configureAudioSession()
    let u = AVSpeechUtterance(string: text)
    u.voice = AVSpeechSynthesisVoice(language: "en-US")
    log.add("speech: \"\(text.prefix(60))\" route: \(routeDescription) a2dp=\(isOnBluetoothA2DP)")
    synth.speak(u)
  }

  // MARK: AVSpeechSynthesizerDelegate

  nonisolated func speechSynthesizer(_ s: AVSpeechSynthesizer, didStart u: AVSpeechUtterance) {
    SpikeLog.shared.add("speech: started")
  }

  nonisolated func speechSynthesizer(_ s: AVSpeechSynthesizer, didFinish u: AVSpeechUtterance) {
    SpikeLog.shared.add("speech: finished")
  }
}
