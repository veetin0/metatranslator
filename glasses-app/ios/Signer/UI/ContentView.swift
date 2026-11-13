import SwiftUI
import UIKit

/// Spike screen: register/connect state, Start/Stop stream, core URL, Hello and Speak test
/// buttons, counters and the spike log. Diagnostic by design (M0 is a go/no-go), but the
/// lens preview uses the DESIGN.md lens colours so the phone shows what the card says.
struct ContentView: View {
  @Bindable var model: SignerViewModel

  var body: some View {
    NavigationStack {
      List {
        streamSection
        lensSection
        replySection
        debugSection
        countersSection
        statusSection
        coreSection
        mockSection
        logSection
      }
      .navigationTitle("Signer spike")
      .navigationBarTitleDisplayMode(.inline)
    }
  }

  // MARK: Status and registration

  private var statusSection: some View {
    Section("Glasses") {
      row("Registration", model.session.registrationState.description)
      row("Device", model.session.device?.name ?? "none")
      if let d = model.session.device {
        row("Link", d.link)
        row("Battery", d.batteryPercent.map { "\($0)%" } ?? "unknown")
        row("Thermal", d.thermal)
        row("Worn / hinge", "\(d.worn) / \(d.hinge)")
        row("Compatibility", d.compatibility)
        row("Display", d.supportsDisplay ? "yes" : "no")
      }
      row("Camera permission", model.session.cameraPermission.rawValue)
      row("Session", model.session.sessionState.description)
      if let e = model.session.lastError {
        Text(e).font(.footnote).foregroundStyle(.red)
      }
      HStack {
        Button("Register") { model.register() }
          .disabled(model.session.registrationState == .registered || model.session.registrationState == .registering)
        Spacer()
        Button("Unregister", role: .destructive) { model.unregister() }
          .disabled(model.session.registrationState != .registered)
      }
      .buttonStyle(.bordered)
    }
  }

  // MARK: Stream

  private var streamSection: some View {
    Section("Stream") {
      row("Stream", "\(model.streamPhase)")
      row("Display", model.displayState)
      Toggle("Fallback plan (low 360x640 @7)", isOn: $model.useFallbackPlan)
        .disabled(model.isRunning)
      Text("Plan: \(model.plan.label)").font(.footnote).foregroundStyle(.secondary)
      if model.isRunning {
        Button(role: .destructive) { model.stopStream() } label: {
          Label("Stop stream", systemImage: "stop.circle.fill").frame(maxWidth: .infinity, minHeight: 44)
        }
        .buttonStyle(.borderedProminent)
      } else {
        Button { model.startStream() } label: {
          Label("Start stream", systemImage: "play.circle.fill").frame(maxWidth: .infinity, minHeight: 44)
        }
        .buttonStyle(.borderedProminent)
      }
    }
  }

  // MARK: Lens

  private var lensSection: some View {
    Section("Lens") {
      LensPreview(card: model.previewCard)
        .listRowInsets(EdgeInsets())
      HStack {
        Button("Show Hello on display") { model.showHello() }
        Spacer()
        Button("Speak test") { model.speakTest() }
      }
      .buttonStyle(.bordered)
      row("Audio route", model.audioRoute)
    }
  }

  // MARK: Reply (M3.1)

  private var replySection: some View {
    Section("Reply") {
      if model.replySTTEnabled {
        HoldToTalkButton(
          phase: model.reply.phase,
          onPress: { model.replyPressBegan() },
          onRelease: { model.replyPressEnded() })
        if !model.reply.partial.isEmpty {
          Text(model.reply.partial).font(.body)
        }
      }
      HStack {
        TextField("Type a reply", text: $model.reply.typed)
          .submitLabel(.send)
          .onSubmit { model.sendTypedReply() }
        Button("Send") { model.sendTypedReply() }
          .buttonStyle(.bordered)
          .disabled(!model.reply.canSendTyped)
      }
      replyMessage
    }
  }

  @ViewBuilder private var replyMessage: some View {
    switch model.reply.phase {
    case .sent(let text):
      Label("Sent: \(text)", systemImage: "checkmark.circle").font(.footnote)
    case .failed(let reason), .unavailable(let reason):
      Label(reason, systemImage: "exclamationmark.triangle")
        .font(.footnote).foregroundStyle(.orange)
    case .sending:
      Label("Sending...", systemImage: "paperplane").font(.footnote)
    case .processing:
      Label("Got it, finishing...", systemImage: "waveform").font(.footnote)
    case .idle, .listening:
      EmptyView()
    }
  }

  // MARK: Debug: trigger a state (demo, screenshots)

  private var debugSection: some View {
    Section {
      ForEach([AppState.permissionDenied, .glassesOff, .coreDown], id: \.self) { s in
        Button {
          model.triggerDebug(s)
        } label: {
          HStack {
            Text(s.label)
            Spacer()
            if model.debugState == s { Image(systemName: "checkmark") }
          }
        }
      }
      Button("Clear forced state") { model.triggerDebug(nil) }
        .disabled(model.debugState == nil)
    } header: {
      Text("Debug: trigger a state")
    } footer: {
      Text("Forces the state on this screen and on the lens card (the lens shows it while streaming).")
    }
  }

  // MARK: Core

  private var coreSection: some View {
    Section("Core (laptop)") {
      TextField("ws://172.20.10.2:8000", text: $model.coreURLText)
        .textInputAutocapitalization(.never)
        .autocorrectionDisabled()
        .keyboardType(.URL)
        .onSubmit { model.applyCoreURL() }
      if !model.coreURLValid {
        Text("Not a usable URL").font(.footnote).foregroundStyle(.red)
      }
      HStack {
        Button("Save URL") { model.applyCoreURL() }
        Spacer()
        Button("Check /health") { model.checkCore() }
      }
      .buttonStyle(.bordered)
      row("Frames socket", "\(model.framesLink)")
      row("Events socket", "\(model.eventsLink)")
      row("Lens state", model.lensState.label)
      if let step = model.appState.nextStep {
        Label(step, systemImage: "exclamationmark.triangle.fill")
          .font(.footnote).foregroundStyle(.orange)
      }
    }
  }

  // MARK: Counters

  private var countersSection: some View {
    let c = model.counters
    return Section("Counters") {
      row("Glasses frames/s (a)", String(format: "%.1f", c.arrivedPerSecond))
      row("Frame size", c.lastWidth > 0 ? "\(c.lastWidth)x\(c.lastHeight), \(c.lastJpegBytes / 1024) KB" : "none")
      row("Frames sent/s (d)", String(format: "%.1f", c.sentPerSecond))
      row("Sent / arrived / dropped", "\(c.sentTotal) / \(c.arrivedTotal) / \(c.droppedTotal)")
      row("Ack RTT last / worst", rtt(c.lastAckRttMs, c.worstAckRttMs))
      row("Captions received", "\(model.captionsReceived)")
      row("Caption age (approx)", model.captionAgeMsApprox.map { "\($0) ms" } ?? "none")
      row("Caption to lens (f)", model.captionToLensMs.map { String(format: "%.0f ms", $0) } ?? "none")
      row("Display send", model.displaySendMs.map { String(format: "%.0f ms", $0) } ?? "none")
      if let s = model.stats { row("Confirmed", "\(s.confirmed)/\(s.total)") }
    }
  }

  // MARK: Mock

  private var mockSection: some View {
    Section("Mock Device Kit (no glasses)") {
      Toggle(
        "Simulated Ray-Ban Display",
        isOn: Binding(get: { model.mockEnabled }, set: { model.setMock($0) })
      )
      .disabled(model.isRunning)
      Picker("Camera feed", selection: $model.mockFeed) {
        Text("Bundled clip").tag(MockDeviceRepository.Feed.clip)
        Text("Phone back camera").tag(MockDeviceRepository.Feed.phoneBackCamera)
      }
      .onChange(of: model.mockFeed) { _, _ in model.applyMockFeed() }
      if model.mockEnabled {
        MockDisplayPreview(model: model)
          .frame(height: 240)
          .listRowInsets(EdgeInsets())
        Button("Start Chrome preview server (simulator)") { model.startChromePreview() }
          .buttonStyle(.bordered)
      }
    }
  }

  // MARK: Log

  private var logSection: some View {
    Section {
      ForEach(Array(model.logLines.suffix(80).enumerated().reversed()), id: \.offset) { _, line in
        Text(line).font(.system(size: 11, design: .monospaced)).textSelection(.enabled)
      }
    } header: {
      HStack {
        Text("Spike log")
        Spacer()
        Button("Clear") { model.clearLog() }.font(.footnote)
      }
    }
  }

  // MARK: Helpers

  private func row(_ title: String, _ value: String) -> some View {
    HStack {
      Text(title).foregroundStyle(.secondary)
      Spacer()
      Text(value).multilineTextAlignment(.trailing)
    }
    .font(.subheadline)
  }

  private func rtt(_ last: Double?, _ worst: Double) -> String {
    guard let last else { return "none" }
    return String(format: "%.0f / %.0f ms", last, worst)
  }
}

/// Press and hold to talk; release to send. Touch-down and release come from a zero-length
/// long press, so no drag distance cancels it. VoiceOver gets a plain toggle action.
struct HoldToTalkButton: View {
  let phase: ReplyComposer.Phase
  let onPress: () -> Void
  let onRelease: () -> Void
  @State private var held = false

  private var listening: Bool { phase == .listening }

  var body: some View {
    Label(listening ? "Listening... release to send" : "Hold to talk",
          systemImage: listening ? "mic.fill" : "mic")
      .frame(maxWidth: .infinity, minHeight: 56)
      .foregroundStyle(.white)
      .background(listening ? Color.red : Color.accentColor, in: RoundedRectangle(cornerRadius: 12))
      .contentShape(Rectangle())
      .onLongPressGesture(minimumDuration: 0, maximumDistance: .infinity, pressing: { down in
        if down, !held {
          held = true
          onPress()
        } else if !down, held {
          held = false
          onRelease()
        }
      }, perform: {})
      .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
      .accessibilityLabel("Hold to talk")
      .accessibilityAddTraits(.isButton)
      .accessibilityAction(named: listening ? "Stop and send" : "Start talking") {
        if listening { onRelease() } else { onPress() }
      }
  }
}

/// Phone-side picture of the lens card in the DESIGN.md colours (black, white, amber, dim).
struct LensPreview: View {
  let card: LensCard

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      Text(card.stateLine)
        .font(.system(size: 14))
        .foregroundStyle(Color(hex: "#9AA4B2"))
      Spacer(minLength: 0)
      ForEach(Array(card.lines.enumerated()), id: \.offset) { _, line in
        Text(line)
          .font(.system(size: 28, weight: .semibold))
          .foregroundStyle(Color(hex: card.tone.hex))
      }
      Spacer(minLength: 0)
      if let footer = card.footer {
        Text(footer)
          .font(.system(size: 14))
          .foregroundStyle(Color(hex: "#9AA4B2"))
          .frame(maxWidth: .infinity, alignment: .center)
      }
    }
    .padding(16)
    .frame(maxWidth: .infinity, minHeight: 150, alignment: .leading)
    .background(Color.black)
    .accessibilityElement(children: .combine)
    .accessibilityLabel("Lens preview: \(card.lines.joined(separator: " "))")
  }
}

/// In-app render of the Mock Device Kit display (the simulated lens).
struct MockDisplayPreview: UIViewRepresentable {
  let model: SignerViewModel

  func makeUIView(context: Context) -> UIView {
    model.makeMockPreview() ?? UIView()
  }

  func updateUIView(_ uiView: UIView, context: Context) {}
}

extension Color {
  /// `#RRGGBB`
  init(hex: String) {
    let s = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
    var v: UInt64 = 0
    Scanner(string: s).scanHexInt64(&v)
    self.init(
      red: Double((v >> 16) & 0xFF) / 255, green: Double((v >> 8) & 0xFF) / 255,
      blue: Double(v & 0xFF) / 255)
  }
}
