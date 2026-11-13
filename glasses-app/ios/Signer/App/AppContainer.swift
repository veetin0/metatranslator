import Foundation

/// Composition root (BirdSpotter's AppContainer): every long-lived object, built once, plain
/// init injection. Built after `Wearables.configure()` (see SignerApp), because the Mock
/// Device Kit configures DAT itself if nothing has.
@MainActor
final class AppContainer {
  let session: SessionRepository
  let camera: CameraRepository
  let display: DisplayRepository
  let mock: MockDeviceRepository
  let client: CoreClient
  let pipeline: FramePipeline
  let speech: SpeechService
  let viewModel: SignerViewModel

  init() {
    let defaults = UserDefaults.standard
    let wantsMock =
      ProcessInfo.processInfo.arguments.contains("--mock")
      || defaults.bool(forKey: MockDeviceRepository.defaultsKey)

    mock = MockDeviceRepository()
    if wantsMock { mock.enableAndPair() }

    session = SessionRepository()
    camera = CameraRepository()
    display = DisplayRepository()
    // Launch arguments for hands-free runs (simulator, CI): `--core ws://127.0.0.1:8000`, `--mock`,
    // `--autostart` (see the runbook).
    let args = ProcessInfo.processInfo.arguments
    let argCore = args.firstIndex(of: "--core").flatMap { args.indices.contains($0 + 1) ? args[$0 + 1] : nil }
    let base = argCore ?? defaults.string(forKey: SignerViewModel.coreURLKey) ?? CoreEndpoints.defaultBase
    client = CoreClient(endpoints: CoreEndpoints(base) ?? CoreEndpoints(CoreEndpoints.defaultBase)!)
    pipeline = FramePipeline(client: client)
    speech = SpeechService()
    viewModel = SignerViewModel(
      session: session, camera: camera, display: display, mock: mock,
      client: client, pipeline: pipeline, speech: speech, mockEnabled: wantsMock,
      coreURL: base)
    if args.contains("--autostart") {
      Task { @MainActor [viewModel] in
        try? await Task.sleep(nanoseconds: 2_000_000_000)
        viewModel.startStream()
      }
    }
  }
}
