import AVFoundation
import Foundation
import Speech

/// Push-to-talk reply on the PHONE microphone with Apple's Speech framework
/// (`SFSpeechRecognizer`, on-device when the device supports it). `MWDATSpeech` is not used:
/// DAT 1.0.1 ships only MWDATCore/Camera/Display/MockDevice products here (no speech module),
/// and the glasses microphone would force the HFP profile (mono, exclusive with A2DP).
///
/// Audio session while the mic is open: `.playAndRecord` with `.allowBluetoothA2DP` and NOT
/// `.allowBluetooth`, so the glasses stay the A2DP output and the input stays the phone's
/// built-in mic. When recording ends the session goes back to `.playback` (SpeechService).
/// Whether the glasses really keep A2DP during the recording is a G3 hardware check.
///
/// Flow: `start()` -> `onPartial` while speaking -> `stop()` (button released) -> `onFinal`
/// once with the final transcript (or the last partial after `finalTimeout`), or `onError`.
@MainActor
final class ReplyRecognizer {
  var onPartial: ((String) -> Void)?
  /// Final transcript; may be empty when nothing was heard.
  var onFinal: ((String) -> Void)?
  /// Permission denied, recogniser unavailable, audio engine failure: plain sentence.
  var onUnavailable: ((String) -> Void)?

  static let finalTimeout: TimeInterval = 1.5

  private let recognizer: SFSpeechRecognizer?
  private let engine = AVAudioEngine()
  private var request: SFSpeechAudioBufferRecognitionRequest?
  private var task: SFSpeechRecognitionTask?
  private var lastPartial = ""
  private var listening = false
  private var finished = true
  private var timeout: Task<Void, Never>?
  private let log = SpikeLog.shared

  init(locale: Locale = Locale(identifier: "en-US")) {
    recognizer = SFSpeechRecognizer(locale: locale)
  }

  var isListening: Bool { listening }

  /// Asks for permissions the first time, then opens the mic.
  func start() async {
    guard !listening, finished else { return }
    guard let recognizer, recognizer.isAvailable else {
      onUnavailable?("Speech recognition is not available right now. Type your reply instead.")
      return
    }
    guard await Self.authorised() else {
      onUnavailable?("Speech or microphone access is off. Allow it in Settings, or type your reply.")
      return
    }
    do {
      try beginRecording(with: recognizer)
    } catch {
      log.add("reply stt: could not start: \(error.localizedDescription)")
      teardownAudio()
      onUnavailable?("Could not open the microphone. Type your reply instead.")
    }
  }

  /// Button released: close the mic and wait for the final transcript.
  func stop() {
    guard listening else { return }
    listening = false
    engine.stop()
    engine.inputNode.removeTap(onBus: 0)
    request?.endAudio()
    timeout = Task { [weak self] in
      try? await Task.sleep(nanoseconds: UInt64(Self.finalTimeout * 1_000_000_000))
      guard !Task.isCancelled else { return }
      self?.finish(with: self?.lastPartial ?? "")
    }
  }

  func cancel() {
    timeout?.cancel()
    listening = false
    finished = true
    task?.cancel()
    teardownAudio()
  }

  // MARK: Private

  private static func authorised() async -> Bool {
    let speech = await withCheckedContinuation { (c: CheckedContinuation<Bool, Never>) in
      SFSpeechRecognizer.requestAuthorization { c.resume(returning: $0 == .authorized) }
    }
    guard speech else { return false }
    return await AVAudioApplication.requestRecordPermission()
  }

  private func beginRecording(with recognizer: SFSpeechRecognizer) throws {
    let session = AVAudioSession.sharedInstance()
    try session.setCategory(
      .playAndRecord, mode: .default, options: [.allowBluetoothA2DP, .defaultToSpeaker])
    try session.setActive(true, options: .notifyOthersOnDeactivation)
    // Phone mic, even if the glasses are connected.
    if let builtIn = session.availableInputs?.first(where: { $0.portType == .builtInMic }) {
      try? session.setPreferredInput(builtIn)
    }

    let req = SFSpeechAudioBufferRecognitionRequest()
    req.shouldReportPartialResults = true
    req.requiresOnDeviceRecognition = recognizer.supportsOnDeviceRecognition
    request = req
    lastPartial = ""
    finished = false

    task = recognizer.recognitionTask(with: req) { [weak self] result, error in
      let text = result?.bestTranscription.formattedString
      let isFinal = result?.isFinal ?? false
      let failed = error != nil
      Task { @MainActor [weak self] in
        guard let self, !self.finished else { return }
        if let text, !text.isEmpty {
          self.lastPartial = text
          self.onPartial?(text)
        }
        // After stop(), the final result (or an error) closes the flow.
        if (isFinal || failed) && !self.listening { self.finish(with: self.lastPartial) }
      }
    }

    let input = engine.inputNode
    let format = input.outputFormat(forBus: 0)
    input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak req] buffer, _ in
      req?.append(buffer)
    }
    engine.prepare()
    try engine.start()
    listening = true
    log.add("reply stt: listening (on-device: \(recognizer.supportsOnDeviceRecognition))")
  }

  private func finish(with text: String) {
    guard !finished else { return }
    finished = true
    timeout?.cancel()
    task?.cancel()
    teardownAudio()
    log.add("reply stt: final \"\(text.prefix(60))\"")
    onFinal?(text)
  }

  private func teardownAudio() {
    if engine.isRunning { engine.stop() }
    engine.inputNode.removeTap(onBus: 0)
    request = nil
    task = nil
    // Back to output only, so the glasses speaker keeps the A2DP route for captions.
    let s = AVAudioSession.sharedInstance()
    try? s.setCategory(.playback, mode: .spokenAudio, options: [])
    try? s.setActive(true, options: .notifyOthersOnDeactivation)
  }
}
