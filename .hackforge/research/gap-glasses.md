# Gap check: glasses side vs OBJECTIVE (2026-11-13)

Legend: **[V]** read on an official Meta page this session (or earlier research, cited); **[?]** docs silent, must be tested on device. The WebFetch summaries this session were thin: the Web Apps and DAT pages name no key/event identifiers, so those are flagged [?] rather than guessed.

## 1. Camera access (answer: NOT from the Web App)
- Web Apps on Ray-Ban Display get position, location, wrist motion, text input. No camera, mic or getUserMedia. [V] https://developers.meta.com/wearables/faq/ and https://wearables.developer.meta.com/docs/develop/webapps (earlier research: platform.md §1A, webapps-and-datasets.md §1). The Build overview page does not list camera at all (checked today).
- Supported route: DAT in a native phone app. Camera stream plus standalone photo capture. [V] https://wearables.developer.meta.com/docs/develop/dat/build-overview/ . Photo capture and camera audio are Experimental (cannot publish); camera streaming and Inputs are not [V] https://github.com/facebook/meta-wearables-dat-ios README.
- Stream settings: `StreamConfiguration(videoCodec: .hvc1, resolution, frameRate)`; BirdSpotter uses `.hvc1`, `.low`, 7 fps and `.hvc1` keeps flowing when backgrounded [V BirdSpotter, webapps-and-datasets.md §4]. Max 720x1280, default 504x896 [2nd].
- How video reaches FastAPI: iOS app receives `VideoFrame` (`CMSampleBuffer`) -> (a) our current contract: JPEG per frame over WS `/ws/frames` (CONTRACTS §3; implemented in `glasses-app/ios/Signer/Net/FramePipeline.swift`, `FramePacking.swift`), or (b) OBJECTIVE style: buffer frames between Start/Stop into an MP4/HEVC file with `AVAssetWriter` and `POST` multipart to a REST endpoint. Both are plain HTTP/WS from the phone; the glasses link is Bluetooth/Wi-Fi into the phone only.
- Camera + display in the same session on Ray-Ban Display: docs silent [?]; the display page says exclusive control of the *display* only (fetched today). BirdSpotter code attaches both to one `DeviceSession` (inferred). Spike G1 on hardware decides.

## 2. Neural Band start/stop gesture
- **Web App:** Neural Band is an input device that the system turns into D-pad/navigation: "The browser spatially navigates semantic, visible controls and activates the selected control" [V web apps build overview]. No Neural-Band-specific API or event is documented; key names not stated on the page [?] (earlier research: arrows + Enter). Nearest control: a big focused `<button>` the wearer activates with the Neural Band select (pinch) = "Start recording / Stop". So gesture is supported only as generic **select on a focused button**, not a dedicated "record" gesture.
- **DAT iOS:** "Inputs: receive navigation, button, capture, and drag interactions from glasses", not marked experimental in the README fetched today [V]. A "capture" interaction exists, so a capture gesture reaching the phone app could toggle recording. Exact type/event names are not on the README or display-overview page [?]; the earlier BirdSpotter notes called Inputs Experimental (conflict - treat as experimental, fine for a hackathon). Mapping a specific Neural Band gesture to "capture" is not documented [?]. DAT also supports a `Button` display element with tap handlers [V display-overview]: a DAT Display "Record/Stop" button tapped with the Neural Band is the safest supported control.
- Fallback: Start/Stop button in the iOS app and in the Signer Card (already built).

## 3. Returned audio in the Web App
- Documented: "A supported subset of `speechSynthesis` speaks concise content through the glasses speaker" [V build overview]; earlier research: one English voice, no permission prompt, volume ignored, plays through the glasses speaker [V webapps-and-datasets.md §1]. Docs say speech must not be the only channel.
- `HTMLAudioElement`/WebAudio: **not listed either way** [?]. The earlier web-apps page said audio playback with volume/mute through glasses speaker (platform.md §1A, garbled wording). Autoplay without user gesture [?]. Must feature-test on device/simulator.
- Sound exits the **glasses speaker** for Web App audio [V]; for phone-played audio (iOS app) it goes to the glasses only via Bluetooth A2DP/HFP routing; there is no DAT speaker API [V BirdSpotter `SystemSpokenOutput.swift`].
- Consequence for "Gemini TTS audio": returned WAV/MP3 can't be assumed to play in the Web App. Safer: iOS app plays it with `AVAudioPlayer` (route = glasses), Web App tries `Audio` and falls back to `speechSynthesis`.

## 4. What we built vs OBJECTIVE (frontend points)

| # | OBJECTIVE point | Status | Evidence |
|---|---|---|---|
| 1 | Meta Wearables Web App, HTML/CSS/JS | MATCHES | `hud-web/index.html:6` (`mrbd-web-app-capable`), `hud-web/src/main.js` |
| 2 | Record start/stop via Neural Band gesture (if supported) | MISSING in Web App; PARTIAL elsewhere | Web App has no Start/Stop control (`main.js:66-81` only veto + arrows). Start/Stop exists in card (`card/app.js:119-120`) and iOS app (`UI/ContentView.swift:66-72`, `SignerViewModel.swift:149,177`) as phone buttons; no DAT Inputs/Neural Band handling (grep of `glasses-app/ios/Signer` finds none) |
| 3 | Verify camera access, use DAT via mobile | MATCHES | `glasses-app/ios` (DAT camera, `Dat/CameraRepository.swift`; README states hardware unverified) |
| 4 | Video captured -> backend REST upload | PARTIAL | We stream JPEG over WS `/ws/frames` (CONTRACTS §2-3), no clip POST and no `/translate`-style endpoint. OBJECTIVE says avoid streaming. |
| 5 | Display translated English text | MATCHES | `hud-web/src/lens.js:70-80,91-93`, `main.js:13-25`; DAT card `Logic/LensCard.swift` |
| 6 | Play returned audio | PARTIAL | Only local `speechSynthesis` for `speak:true` (`main.js:30-38`, `lens.js:96-98`; iOS `Audio/SpeechService.swift`). Server-returned audio (Gemini TTS) not consumed; contract has no audio field |
| 7 | Minimal readable UI | MATCHES | `lens.js:3-4` 24 chars x 2 lines, 600x600 |
| 8 | Clearly indicate uncertain predictions | MATCHES | tiers: `lens.js:72-78` (amber "?" + "or" alternatives, not spoken), card `CONF` `card/app.js:11`, `captionHtml:32-48` |
| 9 | State / consent visibility | MATCHES (extra) | `lens.js:60-68`, `card/app.js:21-30` ON light |
| 10 | Loading/processing state after Stop ("translating...") | MISSING | no `processing` state in `STATE_LABEL` (`lens.js:6-14`); `partial` ignored by lens (`lens.js:35`) |
| 11 | No databases/auth | MATCHES | none in front-ends |

## 5. Smallest changes (hours)

1. **Record/stop flow in Web App (1-1.5 h).** Add a focus-first `Record` / `Stop` button (>= 88 px, `data-focus`) in `hud-web` that `POST`s `/session/start|stop` (`by:"hud"` needs a contract tweak: `by` currently `card|app`; lead decision, or use `"app"`). Select via Neural Band = standard activation of focused button [V]. Test in Display Simulator D-pad/Enter. Add `recording` / `translating` state label.
2. **Neural Band capture in iOS app (2-3 h, risky).** Subscribe to DAT Inputs (find exact API in the DAT iOS API reference / `search_dat_docs`) and toggle `startStream/stopStream` on a capture event; fallback = DAT Display `Button` "Record/Stop" (1 h) and existing phone buttons. Hardware-gated.
3. **Clip upload path (3-4 h, backend + iOS).** iOS records frames between Start/Stop into an MP4 (`AVAssetWriter`) and `POST /translate` multipart; core returns `{caption event, audio_url}` (lead must freeze this contract; backend owns `/translate`). Cheaper alternative (0 h): keep the WS stream and treat Start..Stop as the clip, with the core emitting the caption at Stop; only deviates from OBJECTIVE wording. Recommend the lead picks one.
4. **Show text + play returned audio (1.5-2 h).** Add optional `audio_url` (or base64) to the `caption` event; `hud-web`: `new Audio(url).play()` in try/catch, fall back to `speechSynthesis` if it rejects or `Audio` is unsupported; iOS: `AVAudioPlayer` on the Bluetooth route. Feature-detect and log result in the simulator and on glasses [?].
5. **Uncertain shown clearly (0.5 h).** Already works; add a visible "Low confidence, not spoken" label and show the confidence % in the lens; reject (`none`) already shows "Didn't catch that" per contract.
6. **Processing/loading indicator (0.5 h).** Show "Translating..." between Stop and caption (needs a `state` value or reuse `partial`; contract change or client-side timer).

## 6. Risks / tests to run on hardware (first)
- Camera and display in one session; `Audio`/WebAudio on the Web App; Inputs event names; phone TTS routing to glasses; Web App public HTTPS hosting + WSS to core.
- Tool limits today: pages summarized by a small model; none of the Meta pages we fetched named Neural Band event identifiers. Confirm via `search_dat_docs` / `search_webapps_docs` (Wearables docs MCP) and the DAT API reference before coding items 2 and 4.
