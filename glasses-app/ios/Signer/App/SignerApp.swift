import MWDATCore
import SwiftUI

@main
struct SignerApp: App {
  /// Built at the end of `init`, after `Wearables.configure()`: the Mock Device Kit may be
  /// switched on while the container is built and would configure DAT itself, making a later
  /// `configure()` a crash (BirdSpotterApp.swift has the same note).
  @State private var container: AppContainer

  init() {
    do {
      try Wearables.configure()
    } catch {
      // A misconfigured Info.plist (MWDAT keys). Do not crash the spike: the screen shows it.
      SpikeLog.shared.add("DAT configure failed: \(error)")
      NSLog("[Signer] DAT configure failed: \(error)")
    }
    _container = State(initialValue: AppContainer())
  }

  var body: some Scene {
    WindowGroup {
      ContentView(model: container.viewModel)
        .preferredColorScheme(.dark)
        .onOpenURL { url in
          // The way back from the Meta AI app after registration or a permission request.
          Task { await container.session.handle(url: url) }
        }
    }
  }
}
