# Web Apps on Ray-Ban Display + English (ASL) datasets

Lead request 2026-11-13: use Meta's docs on how the app gets onto the glasses, use the open display simulators so we can develop without glasses, and find datasets for sign language → English (English only).

## 1. How our app gets onto the glasses (Web App path)
Source: https://wearables.developer.meta.com/docs/develop/webapps , /webapps/build/ , /webapps/test/ , https://developers.meta.com/wearables/faq/
- A Web App is plain HTML/CSS/JS that runs **on the glasses' display**. No native app or SDK is needed for display, and no store review is needed for dev use; unreviewed apps are labelled "unverified".
- **Hosting:** "must be hosted on a publicly accessible HTTPS URL". A valid TLS certificate is required and HTTP-only URLs are not supported. A LAN IP or localhost won't work. A public HTTPS tunnel (cloudflared/ngrok) or static hosting (Vercel/GitHub Pages) should work, but that's our inference; M0 checks it.
- **Minimum versions:** glasses software v125+, Meta AI app v272+. DAT needs higher versions anyway: app V292, firmware V128.
- **Developer Mode:** Meta AI app → Settings → App Info → tap **App version** 5× → Enable.
- **Install:**
  - **By URL:** App Settings → Apps → Web Apps → **Connect Web App** → enter the HTTPS URL → Save. It appears at the bottom of the app grid. Other doc pages give slightly different menu paths.
  - **By QR:** encode `fb-viewapp://web_app_deep_link?appName=<name>&appUrl=<https-url>`. The simulator's "View on Glasses QR" button generates it. This is how a judge or a pilot user installs it: our "real app on the glasses" story.
- **Head tags:** `<meta name="mrbd-web-app-capable" content="yes">` and `<meta name="description">`. A manifest is optional, for icons only (PNG ≥ 52×52, no SVG).
- **APIs available:**
  - `fetch` and **WebSocket**, over the glasses' Wi-Fi or the phone tether.
  - `window.speechSynthesis` plays **through the glasses speaker**: one English voice, no permission prompt, `volume` ignored. It is feature-gated, so we verify on our device.
  - localStorage, Service Worker/Cache, IMU, geolocation.
- **Not available:** **camera, microphone, getUserMedia, notifications.** Voice only comes in through system dictation into text inputs. So a Web App can show and speak our captions, but it **cannot see the signer**. Camera frames still need DAT on the phone.
- **Display rules:**
  - Viewport is 600×600, with no scrolling.
  - **Pure black is transparent**, so we design for an additive display.
  - Text sizes: body text ≥ 16 px, primary text 20–24 px. Focus targets ≥ 88 px.
  - Input is limited to Arrow keys + Enter (D-pad / Neural Band). Back calls `history.back()`.
- **Performance:** first load < 300 KB, < 15 requests, slow link (1 KB ≈ 16 ms), 30 Hz panel, so no 60 fps loops.

## 2. Simulators and repos (develop without glasses)
- **Meta Ray-Ban Display Simulator** (Chrome extension): https://chromewebstore.google.com/detail/jpjlmmodokemlepklkdbimceggpbjcll
  - Gives a 600×600 additive frame over a background (image, animation or **live webcam**).
  - Has D-pad and Select buttons that send key events.
  - Has brightness, blur and auto-dim controls, a WebM recorder (useful for the backup video), the install QR and a QA checklist.
  - We found no separate GitHub repo for the simulator itself.
- **Starter kit + Claude Code plugin:** https://github.com/meta/meta-wearables-webapp (formerly facebookincubator/…)
  - Install it as a plugin: `/plugin marketplace add https://github.com/meta/meta-wearables-webapp`, then `/plugin install meta-wearables-webapp@meta-wearables`.
  - Skills: `ai-glasses-webapp-build/-ui/-device/-test/-optimize-performance/-publish` (publish writes `qr-publish.png`).
  - Templates are React + Vite + TS on the UI Toolkit (https://github.com/meta/meta-ray-ban-display-ui-toolkit-web). Example: `examples/snake`.
- **Docs MCP (no auth):** `claude mcp add --transport http wearables https://mcp.developer.meta.com/wearables`. Tools: `search_webapps_docs`, `search_dat_docs`.
- **DAT Mock Device Kit (Android)**, for testing the camera and DAT display without glasses:
  - **Camera:** `setCameraFeed(fileUri)` plays a video file as the glasses camera, so we can feed recorded signing clips. `setCameraFeed(CameraFacing)` uses the phone camera instead.
  - **Display:** to show the DAT display in Chrome, run `startTestServer(9000)` + `adb forward tcp:9000 tcp:9000` and open `http://127.0.0.1:9000/` with the simulator extension. For an in-app preview, use `createPreviewView(context)`.
  - DAT repos: https://github.com/facebook/meta-wearables-dat-android , https://github.com/facebook/meta-wearables-dat-ios
- **Still unknown in the docs**, so M0 checks them on hardware:
  - Whether DAT camera + DAT display can run together.
  - Whether a Web App can stay open while the phone streams the DAT camera.
  - How phone TTS audio is routed to the glasses.
  - Web App background/timeout behaviour.

## 4. Meta's reference glasses app: DAT iOS `samples/BirdSpotter`
Source: https://github.com/meta/meta-wearables-dat-ios/tree/main/samples/BirdSpotter (README, Info.plist, `Data/Dat/*`, `Data/Audio/SystemSpokenOutput.swift`, `Features/Identify/RealtimeViewModel.swift`, CHANGELOG). Two of those files were only partly read, about 39K of 115K characters.

**What the sample does**
- Bird identification is **simulated** by a scripted `PresetDemoDirector`, with no ML, server or LLM. The sample shows app structure, not computer vision.
- The video half of its camera stream is never looked at; it exists to wake the sensor and carry the glasses mic.

**Structure**
- `AppContainer` is the composition root.
- `Data/Dat/` holds the session, camera, display, input, motion, speech, voice and mock-device repositories.
- `RealtimeViewModel` routes cards to the glasses only while `isDisplayAvailable && isGlassesSessionLive`.

**Camera + display in one session**
- `activeCamera` and `activeDisplay` sit on the same `DeviceSession`, and the display attaches once the stream reaches `.streaming`. This is inferred from the code; we haven't seen it on hardware.
- Stream settings: `StreamConfiguration(videoCodec: .hvc1, audioCodec: .pcm 16 kHz mono, resolution: .low, frameRate: 7)`.
  - `.hvc1` keeps flowing when the app is backgrounded; `.raw` pauses.
  - Medium = 504x896 and high = 720x1280, but `.low` dimensions aren't stated.
  - Frames and still photos compete for the same sensor.

**Display**
- `MWDATDisplay` `FlexBox{Text(.heading), Text(.meta), Image, Text(.body)}.padding(16)` sent with `sendThroughActiveDisplay`.
- The canvas is 600×600, and every send replaces the whole screen.

**Audio**
- `AVSpeechSynthesizer` (en-US) speaks only when the audio route includes Bluetooth A2DP/HFP/LE. The glasses are the phone's Bluetooth speaker; there is no DAT speaker API.
- The glasses mic arrives on the camera stream (Meta AI `.microphone` permission). `FailoverAudioSource` falls back to the phone mic.
- `MWDATSpeech` does on-device speech-to-text.

**Experimental features**
- Inputs, Motion, Speech, Photo, Camera audio and Voice invocation are Experimental: apps that use them can't be published yet.
- Camera streaming and Display are not experimental.

**Setup**
- iOS 17.2+ (BirdSpotter README says 18+). Swift Package `https://github.com/facebook/meta-wearables-dat-ios`, SDK 1.0.1.
- Info.plist `MWDAT` dict: `MetaAppID`=0, `ClientToken`=0 in Developer Mode, `TeamID`, `AppLinkURLScheme`, analytics opt-out. `UIBackgroundModes` and `com.meta.ar.wearable` accessory protocol.
- Change the bundle ID to your team's.
- Whether a free personal team gets frames isn't stated. A 2nd-hand report says it doesn't (platform.md). M0 checks this.

**Other samples**
- `CameraAccess` actually consumes video frames: live preview, photos, recording.
- `DisplayAccess` sends interactive display views. An iOS Simulator build can stream them to the Chrome Display Simulator; a physical iPhone can't.
- Mock Device Kit supports `metaRayBanDisplay` since 1.0.0. This corrects platform.md's "no display mock".

**For Signer**
- Copy BirdSpotter's structure and display/TTS wiring.
- Take frame handling from `CameraAccess`: take the `VideoFrame`'s `CMSampleBuffer` and send it to the core.
- On-device Apple Vision hand pose is possible later but not planned.

## 3. Datasets: sign language → English
"English sign language" here means **ASL (American Sign Language) glossed into English**, the language with the open datasets. BSL (British) data exists (BOBSL, BSL-1K), but it is BBC/Oxford-licensed, research-only and video-only, so not used. FinSL is dropped from the plan.

| Dataset | Size | Format | Licence | Use for us |
|---|---|---|---|---|
| **Google Isolated Sign Language Recognition (Kaggle `asl-signs`, from PopSign)** | ~94k clips, 250 signs, ~21 signers; 40 GB zip / 57 GB extracted | **MediaPipe Holistic landmarks already extracted** (543 landmarks × xyz per frame, parquet). This is the same feature space as our pipeline, so no video processing is needed. | Kaggle competition data. Login + accepting the rules are needed; the licence (believed CC BY 4.0) is to be confirmed in M0. | **Main pretraining set.** Vocabulary is chosen from its 250 signs. |
| **PopSign ASL v1.0** (https://signdata.cc.gatech.edu/view/datasets/popsign_v1_0/) | 200,686 videos, 250 signs, 47 signers | Smartphone selfie video | **CC BY 4.0** | Backup / more signers (we run MediaPipe ourselves) |
| ASL Citizen (Microsoft) | 83,399 videos, 2,731 signs, 52 Deaf/HoH signers, signer-independent splits | Video, public wget zip | Research, non-commercial only | Optional held-out test of unseen signers (non-commercial; eval only) |
| WLASL | 2,000 signs, 21k videos, 119 signers | YouTube URLs (rotting) | C-UDA, academic only | Skip |
| MS-ASL | 1,000 signs, 25k samples, 222 signers | Annotations only | Research | Skip |
| How2Sign | 80 h of continuous ASL + English | Video, keypoints (not MediaPipe) | CC BY-NC | Skip (continuous, too heavy) |

**Update 2026-11-13 (lead):** no Kaggle account, so the Kaggle parquet is out. PopSign v1.0 (same 250 signs, CC BY 4.0) becomes the prior data: we download only the vocabulary signs and extract landmarks ourselves. Its download format is unconfirmed (M0).

**Vocabulary impact:**
- The Kaggle 250 signs are toddler "first words".
- From memory, these overlap the classroom vocabulary: yes, no, please, thankyou, hello, bye, water, drink, hungry, thirsty, finish, wait, potty (bathroom), sick, read, book, pen, pencil, time, where, why, who, think, look, listen, talk, quiet, home, now, later, tomorrow, happy, sad.
- **Verify against `sign_to_prediction_index_map.json` in M0.**
- Classroom signs missing from that set (e.g. help, teacher, understand, again, question) are recorded by the team or added with Teach-a-sign.

**Domain shift:**
- Kaggle/PopSign are selfie-camera, mostly one-handed, at arm's length.
- The glasses camera sees the signer from 1–1.5 m.
- Shoulder-normalised features absorb scale.
- To make the model ignore which hand is dominant, we train with horizontal flips.
- We measure on our own glasses-camera clips (M2).
