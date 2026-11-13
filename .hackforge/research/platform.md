# Meta glasses platform research (as of 2026-11-13)

Legend: **[V]** = read on an official Meta page this session; **[2nd]** = secondary/third-party source; **[?]** = not found / unverified, test on device.

## TL;DR
- Camera = **DAT only** (iOS/Android phone app). Web Apps on Ray-Ban Display have **no camera and no raw mic**.
- DAT 1.0 (stable, Sept 2026) **can also draw on the Ray-Ban Display** (FlexBox/Text/Image/Button/Icon, 600x600) and play audio. So one native phone app can do camera-in -> cloud ML -> text on HUD + TTS. Older articles saying "DAT can't show anything on the HUD" are stale.
- Biggest unknown: whether camera stream and display can run **in the same session simultaneously** on Ray-Ban Display. Docs don't say. Test this in the first 2 hours.
- Camera stream is low-res (max 720x1280 portrait, 30 fps, Bluetooth-limited; default 504x896). Hand-sign recognition must tolerate this.

## 1. The two integration paths

### A. Web Apps (Ray-Ban Display only)
- Standard HTML/CSS/JS running on the glasses, no SDK, no companion app. [V] https://developers.meta.com/wearables/faq/ , https://developers.meta.com/wearables/web-apps/
- Display: 600x600 additive display (dark = transparent; use bright high-contrast). [V] web-apps page
- Input: D-pad/arrow keys + Enter, pinch-and-drag (opt-in), Neural Band optional but recommended (gestures, handwriting); text via dictation / handwriting / on-screen keyboard. [V]
- Sensors: W3C device motion/orientation; location from phone (permission). [V]
- Network: `fetch` and `WebSocket` over glasses Wi-Fi or phone tether; service workers/Cache API offline. [V]
- Audio: playback through glasses speaker with volume/mute control. [V web-apps page] (page wording on "speaking text" is garbled - test `speechSynthesis` / `<audio>` on device **[?]**)
- **Camera / raw mic: not available** (page doesn't list them; FAQ says Web Apps get position, location, wrist motion, text input). [V FAQ] [2nd] https://virtual.reality.news/news/meta-ray-ban-display-developer-preview-sdk-paths-and-platform-gaps/
- Load: Dev Mode on -> Meta AI app > App settings > App connections > "Add a Web App", enter HTTPS URL (deeplink/QR also work). [V FAQ]. Browser simulator = Chrome extension "Meta Ray-Ban Display Web App Simulator" (600x600 + D-pad). [V web-apps page]
- Publishing "coming soon"; irrelevant for hackathon. [V FAQ]

### B. Device Access Toolkit (DAT) - mobile integration
- Swift (iOS 17.2+, Xcode 26.4+) and Kotlin (Android 10+, Kotlin 2.2+) SDKs; works with Ray-Ban Meta Gen 1/2, Oakley Meta, **and** Ray-Ban Display. [V] https://wearables.developer.meta.com/docs/develop , repos https://github.com/facebook/meta-wearables-dat-ios , https://github.com/meta/meta-wearables-dat-android
- Capabilities (docs build-overview) [V] https://wearables.developer.meta.com/docs/develop/dat/build-overview/ :
  - **Camera**: video stream + photo capture during stream; choose resolution & fps.
  - **Mic in**: Hands-Free Profile, **8 kHz mono** (voice-grade; phone mic is fine for the hearing user's speech reply path).
  - **Audio out**: through glasses speakers (glasses are also a Bluetooth audio device, so phone TTS can just play to them) [2nd] https://www.uploadvr.com/meta-wearables-device-access-toolkit-public-preview/
  - **Display (Ray-Ban Display only)**: FlexBox, Text (heading/body/meta), Image (URL), Button, Icon, Video (MP4 URL, <400px/side, <=70,000 px). [V] https://wearables.developer.meta.com/docs/develop/dat/display-overview/
  - Inputs: touchpad + Neural Band events (taps, navigation, capture, drag) delivered to the phone app (inputs API is **experimental**). [V display-overview; 2nd] https://mixed-news.com/en/?p=35220
  - Motion/IMU, on-device speech recognition w/ partial+final results (experimental), "Hey Meta" voice invocation. [V] iOS README https://github.com/facebook/meta-wearables-dat-ios
- Camera numbers [2nd, quoting Meta docs] https://mixed-news.com/en/meta-dat-camera-720x1280-lower-resolution-higher-quality/ , https://www.uploadvr.com/meta-wearables-device-access-toolkit-public-preview/ :
  - `.high` 720x1280, `.medium` 504x896 (default), `.low` 360x640 (portrait orientation).
  - fps in {2, 7, 15, 24, 30}. Meta: lower res/fps = *better* quality (less compression). Under bandwidth pressure it lowers res first, then fps "never below 15".
  - Frames as decoded `.raw` or compressed HEVC `.hvc1`. ~450-600 kbps at 720p30 measured by a third party.
  - Latency: **no official figure found [?]** - measure it ourselves.
  - Transport: Meta docs say Bluetooth Classic; iOS integration guide says BLE for control and **Wi-Fi (phone joins glasses-hosted network) for streaming**, needs Local Network + HotspotConfiguration entitlement. If denied, falls back to BLE without streaming. [V] https://wearables.developer.meta.com/docs/develop/dat/build-integration-ios/
- Display display rules [V display-overview]: each send replaces whole display (no partial updates); exclusive display control while session runs; system can interrupt (calls/notifications); display dims/sleeps when idle; back from root view ends session; phone is source of truth; large images lag over Bluetooth -> keep layouts simple (ideal for a text caption).
- Camera + display in one session: **not stated [?]**. Only one session per device at a time; "some features unavailable while a session is active". [V build-overview]. Third-party RN wrapper marks display "wrapped, untested on hardware" [2nd mixed-news ?p=35220].

## 2. Can a web app use the camera? Realistic architecture
- No. So: **Ray-Ban Display -> (Meta AI app/BT/Wi-Fi) -> our phone app (DAT camera stream) -> ML (on-phone or cloud, e.g. Modal/Gemini) -> text back**.
- Return path options:
  1. **DAT Display** from the same phone app (primary). Native, single app.
  2. **Companion Web App on the glasses** that opens a WebSocket to our server and renders captions + plays TTS audio; phone app just streams camera and POSTs results to server. Fallback if camera+display can't share a session (web app is a separate runtime, so no session conflict) **[untested - plausible]**.
  3. TTS spoken on the phone -> routes to glasses speakers over Bluetooth audio (works on Gen 2 without display too = audio-first path).
- Ray-Ban Meta Gen 2 (no display): same DAT camera + audio out; captions only as spoken audio (and phone screen, which is not "glasses" per rule R2 - weak). [V] FAQ "DAT supports both display and displayless glasses".

## 3. Setup steps & gotchas
1. Wearables Developer Center account + project + release channel (for sharing builds; up to 100 test users [2nd] https://developers.meta.com/blog/meta-connect-recap/). Meta AI app Dev Mode: Settings > App Info > tap version 5x > toggle. [V] https://wearables.developer.meta.com/docs/develop
2. Pair glasses in Meta AI app; **version minimums** [V] https://wearables.developer.meta.com/docs/develop/dat/version-dependencies/ : SDK 1.0.1 needs Meta AI app **V292** and Ray-Ban Display firmware **V128**. Check firmware at Devices > device > Device settings > General > About. Update everything before the hackathon starts (shared devices may be on old versions).
3. For Display: DAT must be installed onto the glasses (5-10 s, keep Meta AI app open, glasses worn). [V display-overview]
4. iOS integration [V build-integration-ios]: SPM add `facebook/meta-wearables-dat-ios`; Info.plist `MWDAT` dict (`AppLinkURLScheme`, `MetaAppID`, `ClientToken`, `TeamID`), `UIBackgroundModes` bluetooth-central, `NSBluetoothAlwaysUsageDescription`, `NSLocalNetworkUsageDescription`, `NSBonjourServices` `_bonjour._tcp`, `NSCameraUsageDescription`, custom URL scheme for Dev Mode. Flow: `Wearables.configure()` -> `startRegistration()` -> forward callback URL to `Wearables.shared.handleUrl` -> observe `registrationStateStream()` / `devicesStream()` -> `checkPermissionStatus(.camera)` / `requestPermission(.camera)` (via Meta AI deeplink: allow always / once / deny) -> `createSession(deviceSelector:)` -> `session.start()`.
5. **Gotchas**: a build signed with a **free Apple ID** connects over BLE but never receives frames (lacks Wi-Fi/hotspot entitlement) -> need paid Apple developer team [2nd mixed-news 720x1280]. Only one third-party app registered at a time (registering another drops the previous) [2nd]. No background streaming (keep app foreground) [2nd, Expo wrapper README]. DAT 1.0 had an HEVC buffer-corruption/frame-freeze bug; 1.0.1 has no developer-facing changes [2nd] https://mixed-news.com/en/meta-wearables-device-access-toolkit-1-0-1-hevc-buffer-corruption/ -> prefer `.raw`/lower settings if freezes. Analytics/crash reporting on by default (opt-out keys in Info.plist) [V iOS README]. Mock Device Kit simulates camera etc. but **does not support display glasses** [V FAQ].
6. Session/device state events [V] https://wearables.developer.meta.com/docs/develop/dat/lifecycle-events/ : `DeviceSessionState` = STARTED / PAUSED / STOPPED; pause by touch interactions, other system experiences, etc.; stopped by folding hinges (BT drops), removing glasses (if wear detection on), app removed, connection loss; reason not exposed; don't restart while PAUSED; unfolding does **not** restart the session - start a new one. 1.0 adds device state: battery, charging, don/doff, hinge, thermal level (non-experimental) [2nd mixed-news ?p=35220]; error list reportedly includes `.batteryLow` [2nd]; "camera busy" error name not confirmed **[?]**. Display lifecycle: stopped/starting/started/stopping. This maps directly to rule D3 (device-state handling) - surface each state in the UI.
7. Languages: native Swift/Kotlin are official. React Native: community `expo-meta-wearables-dat` (needs dev build, not Expo Go; RN 0.76+, iOS 17.2) and `react-native-nitro-glasses`; Flutter community plugins. **Unofficial; display unverified on hardware** [2nd] https://mixed-news.com/en/?p=35220 , https://libraries.io/npm/expo-meta-wearables-dat . Recommendation: native Swift (mentors are iOS/Android DAT engineers).
8. Experimental features (standalone photo capture, camera audio streaming, inputs, motion, on-device speech) can be built/tested but **can't be published** [V iOS README] - fine for a hackathon, mention in deck as pilot caveat. Version/doc status conflict: FAQ says 1.0 stable (rollout from 2026-09-30) while READMEs still say "developer preview" [V both].

## 4. Constraints
- Bandwidth: camera stream bound by BT/Wi-Fi link; auto-degrades res then fps (see above). [2nd]
- Thermal/battery: DAT exposes `thermalLevel` and battery state; Meta has a separate "battery, wear, thermal" guide (not fetched) **[?]**. No official max streaming duration found **[?]** - budget: test a 10-15 min continuous stream early; expect warm glasses; plan demo in short bursts (stream on only while "listening to signer").
- Display: dims/sleeps when idle; interruptions by system. [V]
- Privacy LED: capture LED lights whenever camera in use [2nd] https://www.meta.com/actions/responsible-innovation/ ; Meta disables camera if LED tampering detected [2nd] https://vr.org/articles/meta-privacy-led-tamper-update-super-sensing-glasses-2026 . AUP forbids bypassing/obscuring the LED. [V]
- Meta Wearables Developer AUP [V] https://wearables.developer.meta.com/acceptable-use-policy/ (updated 2026-09-22): no surreptitious capture of recognisable audio/video of user or others; no encouraging covert filming or "analyzing people to facilitate unwanted approaches"; no recording in sensitive locations; **no using sensors to uniquely identify people from faces/voices** (exception for accessibility apps with prior Meta approval). Sign recognition is not identification, but **don't do face ID / signer identification, and don't store faces**. The AUP page does not state storage/sharing/consent rules **[?]**.
- Our design implications (R3/J4): visible "signer has consented / tap to start" step, on-screen indicator while streaming, no frame persistence by default, process-and-discard, show confidence, cloud calls only for frames (disclose it). Meta also says the Meta AI app collects info on device-app communication unless opted out [V iOS README].

## 5. Recommended architecture (4 devs, Mac/Xcode, Android possible)
**Primary (shortest path):** native iOS Swift app (paid Apple team required) built from the `samples/DisplayAccess` + camera sample in the DAT repo.
- Module A (1 dev): DAT camera stream `.medium`/15-24 fps -> sample 3-5 fps (or hand-landmark windows) -> POST/WebSocket to server. State UI for registration/permission/session/device events.
- Module B (1 dev): DAT Display screen: big Text caption (latest phrase, confidence chip), "listening/paused/disconnected" states; replace-whole-view updates, throttle to a few updates/s. Plus TTS: `AVSpeechSynthesizer` (or cloud TTS) -> Bluetooth to glasses speaker.
- Module C (1-2 devs): recognition backend (Modal GPU or Gemini on frames; MediaPipe hand/pose landmarks on phone is an option to cut bandwidth) with bounded vocabulary - see sibling research on sign recognition.
- Reply path (I1): hearing person's speech via DAT mic (8 kHz HFP) or phone mic -> STT -> caption for the signer on the phone screen held up / a second device.
- Day-1 first hour spike (go/no-go): (1) update Meta AI app+firmware, Dev Mode, register app; (2) get one camera frame on screen; (3) send "Hello" to the display while stream is running; (4) play TTS to glasses speaker. Record result for decision.

**Fallback A - camera+display can't coexist in one DAT session:** phone app does camera + TTS; captions rendered by a **Web App on the glasses** (fetch/WebSocket to our relay; also can play audio). Web app is simple HTML, easy for any dev; Chrome simulator for dev.
**Fallback B - glasses camera unavailable/frozen/not enough devices:** same pipeline fed from the **phone's back camera or laptop webcam** (pluggable frame source interface); captions still shown on glasses (display or web app) or on a screen; demo honestly as "camera source: phone", with glasses camera as roadmap. Also use Mock Device Kit for camera tests without hardware (no display mock).
**Fallback C - no Display device:** Ray-Ban Meta Gen 2 audio-first: camera via DAT, output spoken TTS only.
- Android alternative (Kotlin) exists with matching samples; pick **one** platform per demo to avoid doubling work; choose iOS if the team has a paid Apple team, else Android (no Wi-Fi entitlement problem) **[assumption]**.

## Open items for the team / organisers (BRIEF Q2-Q4)
- Camera+display concurrent session on Ray-Ban Display: **unknown, spike first**.
- Camera end-to-end latency and sustained streaming duration/thermal: unknown, measure.
- Whether `speechSynthesis`/audio autoplay works in Web Apps: unknown.
- Meta consent guidance beyond AUP: not found; ask mentors. Accessibility-app exception in AUP requires Meta approval only for biometric identification (we don't need it).
- No Junction-specific starter repo found; official samples live in the DAT iOS/Android repos (`samples/`) and a Web Apps starter kit on GitHub (linked from https://developers.meta.com/wearables/faq/). Full docs index for AI tools: https://wearables.developer.meta.com/llms.txt?full=true (Wearables MCP `search_dat_docs`).
