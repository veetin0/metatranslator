# glasses-app: Signer iOS spike (M0.1)

Native iOS app on the Meta Wearables Device Access Toolkit (DAT) 1.0.1, structured like Meta's
BirdSpotter sample. It answers the M0 go/no-go: can one `DeviceSession` stream the glasses
camera **and** draw a DAT Display card, with phone TTS in the glasses speaker and frames looping
to the laptop over USB tethering?

Status: builds and its 64 unit tests pass on Xcode 26.0.1 for the iOS Simulator, and the whole
path (mock glasses camera, Display card next to the stream, frames to a fake core, captions
back, TTS) was run against the Mock Device Kit. **Nothing has run on real glasses yet.** Hardware
checks (a)-(f) happen in glasses slot G1 and are recorded in
`.hackforge/evidence/M0-spike.md`.

## Layout

```
glasses-app/ios/
  project.yml            XcodeGen spec = source of truth (Signer.xcodeproj is generated, committed)
  Signer/
    App/                 SignerApp (configure DAT, onOpenURL), AppContainer (composition root)
    Dat/                 SessionRepository, CameraRepository, DisplayRepository, MockDeviceRepository
    Net/                 CoreClient (URLSessionWebSocketTask), FramePipeline
    Audio/               SpeechService (AVSpeechSynthesizer, A2DP route)
    UI/                  SignerViewModel, ContentView (spike screen)
    Logic/               pure Swift, no DAT: frame packing, event decoding, throttle,
                         tier -> colour, endpoints, stream plan, error triage
    Resources/mock-feed.mov   504x896 hvc1 test pattern for the Mock Device Kit camera
  SignerTests/           XCTest: 64 tests, includes contracts/events.example.jsonl
```

## 1. Prepare the Mac (once)

1. **Xcode >= 26.4** (the lead's Mac has 26.0.1). DAT 1.0.1 documents 26.4 as the minimum
   (the DisplayAccess sample says Xcode 26.4+, Swift 6.3+). The spike did compile and test on
   26.0.1 for the Simulator, but build for the phone with 26.4 as the docs require.
2. `brew install xcodegen` (already at /opt/homebrew/bin/xcodegen).
3. Generate the project (only needed after editing `project.yml`; the generated project is committed):
   ```bash
   cd glasses-app/ios && xcodegen generate
   ```
4. Open `Signer.xcodeproj`, target **Signer**, tab Signing & Capabilities:
   - **Team**: your paid Apple developer team (or put it in `project.yml` as `DEVELOPMENT_TEAM`
     and regenerate). A free Apple ID connects over Bluetooth but gets no camera frames (no
     Wi-Fi hotspot entitlement), so it must be a paid team.
   - **Bundle Identifier**: `com.signer.glasses` by default; change it if it is taken on your team
     (`PRODUCT_BUNDLE_IDENTIFIER` in `project.yml`). The callback scheme `signer://` does not
     depend on it.
   - Keep the capabilities from `Signer.entitlements`: Hotspot Configuration and Access WiFi
     Information. DAT streams video over Wi-Fi that the glasses host, and the phone joins it.
     Xcode's automatic signing adds them to the App ID.
5. Info.plist `MWDAT` keys are already set: `AppLinkURLScheme` `signer://`, `MetaAppID` `0` and
   `ClientToken` `0` (Developer Mode), `TeamID` from `DEVELOPMENT_TEAM`, analytics and crash
   reporting opted out. Also set: Bluetooth, Local Network + `_bonjour._tcp`, camera (mock feed
   only), `NSAllowsLocalNetworking` for `ws://` to the Mac, `UIBackgroundModes` bluetooth-central
   + audio, and the `com.meta.ar.wearable` external accessory protocol.

## 2. Prepare the glasses and phone

1. Meta AI app **>= V292** on the iPhone, glasses firmware **>= V128** (Devices > glasses >
   Device settings > General > About).
2. Meta AI app: turn on **Developer Mode**: Settings > App Info, tap the **App version** five
   times, then use the toggle and tap Enable (DAT getting-started page). The registered app then
   shows under Meta AI settings > App connections > Developer mode apps.
3. Pair the Ray-Ban Display in the Meta AI app. DAT may ask you to install the DAT app on the
   glasses (5-10 s, keep Meta AI open and the glasses worn).
4. Run Signer on the iPhone (Xcode > the iPhone > Run). Tap **Register**: Meta AI opens, confirm,
   and it returns through `signer://`. The "Registration" row must read `registered` and the
   "Device" row must show the glasses. Only one third-party app is registered at a time.
5. iOS prompts: Bluetooth, Local Network (allow both). Camera permission for the **glasses** is asked
   in the Meta AI app the first time you tap Start stream (allow always or once).

## 3. USB tethering and the core

The phone cannot run a Wi-Fi hotspot while it is on the glasses' Wi-Fi, so the laptop gets its
network from the phone over USB.

1. Plug the iPhone into the Mac with a cable. iPhone: Settings > Personal Hotspot > Allow Others
   to Join (needs cellular data). Trust the Mac if asked.
2. On the Mac, System Settings > Network: an "iPhone USB" interface appears. Find the Mac's IP:
   ```bash
   ifconfig | grep -B3 "inet 172.20"      # usually the Mac is 172.20.10.2, the phone 172.20.10.1
   ```
   `172.20.10.2` is the usual address of the Mac on iPhone USB hotspot, but check it every time.
   Whether the phone keeps the glasses' Wi-Fi **and** the USB hotspot at the same time is itself
   something check (d) verifies.
3. Run the core on the Mac so it listens on all interfaces (CONTRACTS section 10; M1 builds it):
   ```bash
   python -m signer_core.relay            # SIGNER_HOST=0.0.0.0 SIGNER_PORT=8000
   ```
   Until the core exists, any server that implements `GET /health`, `POST /session/start`,
   `WS /ws/frames` (binary) and `WS /ws/events` works. Frames are only accepted when the
   session is on, which the app arranges by calling `POST /session/start {"by":"app"}` when you
   tap Start stream. Without a core the glasses checks (a)-(c) still run: frames are counted and dropped.
4. In the app, **Core (laptop)** section: type `ws://<mac ip>:8000`, tap Save URL, then
   **Check /health**. The default is `ws://172.20.10.2:8000`.

## 4. The checks (record each in `.hackforge/evidence/M0-spike.md`)

Run with glasses on, Meta AI app running. Use **Start stream** (Plan shown on screen: medium
504x896 @15 fps raw by default; the **Fallback plan** toggle selects low 360x640 @7).
Keep the "Spike log" section visible; it shows every DAT state and error verbatim.

**(a) Camera medium >= 7 fps.** Start stream. Wait for Stream = `streaming`. Read
*Glasses frames/s* and *Frame size* in Counters for 60 s. Pass: `504x896` and >= 7 fps. If the
size reads 360x640, the link downshifted (note it). Repeat with the fallback plan if (a) fails
at medium.

**(b) DAT Display card while streaming, same session.** After `streaming` the app adds the display
(`display attach result: attached`, `display state: started`). Tap **Show Hello on display**.
Pass: "Hello" is on the lens while the stream keeps running (frames/s do not stop). Note
whether the camera kept going after the display attached. If `addDisplay` fails or the stream
dies, copy the exact log line: that decides Fallback A.

**(c) Phone TTS audible in the glasses speaker while streaming.** Tap **Speak test**. Pass: heard
in the glasses, and *Audio route* reads `BluetoothA2DPOutput`. Also run it with the stream
running, and note if the stream paused.

**(d) Frames to the laptop over USB tethering, captions back.** Core running, URL set. Start stream.
Pass: the core logs frames from the app; *Frames sent/s* is near the glasses rate (>= 7);
*Ack RTT* shows a number; a caption sent by the core shows in Captions received, on the lens
and in the phone Lens preview.

**(e) Web App hello via QR.** Owned by `hud-web/` (M0.2): follow its instructions to install the
hello page on the glasses via the QR / `fb-viewapp://` link and confirm it opens.

**(f) Latency and thermal.** Sign end to lens: sign a sign, stop with a visible end, and time to
the caption showing on the lens (record the screen of a second phone filming the lens, or
use a stopwatch; repeat 5 times, record the median). The app also shows *Caption to lens*
(caption received to DAT send returned, includes the 500 ms throttle) and *Caption age (approx)*.
Then stream continuously for **10 minutes** and write down: glasses temperature by touch,
the Thermal and Battery rows (start vs end), any `thermalHot` / `peakPowerLimit` / `batteryLow`
errors, and whether frames/s fell.

### Watch for CAPABILITY_DENIED

DAT can gate capabilities per user on Meta's servers; a request may be declined at runtime with
`DeviceSessionError.CAPABILITY_DENIED` (docs: version-dependencies). In the Swift 1.0.1 enum
there is no case of that name (it has `noEligibleDevice`, `capabilityAlreadyActive`,
`capabilityNotFound`, `unexpectedError(description:)`, ...), so it can show up under another
name. The app logs every session, camera stream and display error verbatim and, when the text
looks like a denial, adds a `!! CAPABILITY_DENIED suspected` line. If you see it **report it to Meta
immediately** (device, app version, time, the log line) and note it in the spike sheet.

## Without glasses: Mock Device Kit

Toggle **Simulated Ray-Ban Display** in the Mock Device Kit section (or launch with
`--mock`). It pairs a simulated Ray-Ban Display, plays `mock-feed.mov` as the glasses camera,
and shows an in-app preview of the DAT Display below the toggle. Hands-free simulator run:

```bash
xcrun simctl launch booted com.signer.glasses --mock --autostart --core ws://127.0.0.1:8000
```

`--autostart` taps Start stream 2 s after launch. The Chrome display preview (Display Simulator
extension, `http://127.0.0.1:9000/`) works in the iOS Simulator only. The mock does not prove
the real Bluetooth/Wi-Fi bandwidth, the glasses' own refusal rules or the audio route; those are
G1 checks.

## M3.1: reply, D3 states, readout

- **Reply**: the Reply section on the phone has a hold-to-talk button (Apple Speech on the phone
  mic, on-device when supported, `Audio/ReplyRecognizer.swift`) and a typed field. Both
  `POST /reply {text, source:"stt"|"typed"}` (`Logic/ReplyRequest.swift` builds and tests the
  request). `MWDATSpeech` is not used (no such product in DAT 1.0.1 here). Needs the
  microphone and speech permissions (Info.plist strings are in `project.yml`). `--flags teach`
  (or env `SIGNER_FLAGS`) without `reply_stt` hides the mic button.
- **D3 states**: `Logic/AppState.swift` resolves one `AppState` from camera permission, device
  presence, DAT error triage, the events socket and the core's state. Precedence: debug override,
  permission denied, glasses off, core down (only while running), core-reported state.
  `core_down` = events socket down for MORE than 2 s (`CoreLinkMonitor`, injected clock), the
  app reconnects by itself. Each fault shows on the phone and on the lens card (state line plus
  one plain next step) while the DAT display is attached, i.e. while streaming. The **Debug:
  trigger a state** section forces each one for demo and screenshots.
- **Readout footer**: "17/19 confirmed" from `stats` events (DESIGN.md wording), through the
  same 500 ms / on-change throttle as the caption.
- **App to core state message** (contract change pending): `{"type":"state","state":"glasses_off"|
  "permission_denied"|"on","link":"ok","ts":ms,"from":"app"}` on `/ws/events`, behind
  `AppFlags.sendStateToCore` (false). Flip the constant after the lead approves the contract.

## Build and test

```bash
xcodebuild build -quiet -project glasses-app/ios/Signer.xcodeproj -scheme Signer \
  -destination 'generic/platform=iOS Simulator'
xcodebuild test -project glasses-app/ios/Signer.xcodeproj -scheme Signer \
  -destination 'platform=iOS Simulator,name=iPhone 17'
```

## DAT API used (all from the 1.0.1 swiftinterfaces and Meta's samples)

- MWDATCore: `Wearables.configure()`, `Wearables.shared`, `registrationStateStream()`,
  `startRegistration()`, `handleUrl(_:)`, `devicesStream()`, `deviceForIdentifier(_:)`,
  `checkPermissionStatus(.camera)`, `requestPermission(.camera)`, `AutoDeviceSelector(wearables:)`,
  `createSession(deviceSelector:)`, `DeviceSession.start()/stop()/statePublisher/errorPublisher`,
  `Device.addDeviceStateListener`, `ListenerTokenBag`.
- MWDATCamera: `session.addCamera(config:)`, `StreamConfiguration(videoCodec:resolution:frameRate:)`,
  `camera.stream.start()`, `statePublisher`, `videoFramePublisher`, `errorPublisher`,
  `VideoFrame.makeUIImage()`, `camera.stop()`.
- MWDATDisplay: `device.supportsDisplay()`, `session.addDisplay()`, `display.start()`,
  `display.send(FlexBox { Text })`, `display.clearDisplay()`.
- MWDATMockDevice: `MockDeviceKit.shared.enable(config:)`, `pairGlasses(model: .metaRayBanDisplay)`,
  `services.camera.setCameraFeed(fileURL:)`, `services.display.createPreviewView()`,
  `startTestServer(port:)`.
