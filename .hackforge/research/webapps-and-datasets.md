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
