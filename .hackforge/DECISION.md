# Decision

**Build "Signer: Class Bridge" (option A) as the spine, with three grafts from Signer Duet: Teach-a-sign, the live ✓/✗ accuracy readout, and the gloss-only LLM validator.**

## Why
- Same weighted judge score as Duet (7.0) at much higher feasibility (8 vs 5.5); Duet's own M1 is effectively A.
- The grafts are the cheapest J1 (Teach = memorable stage moment + FinSL pilot story) and J4 (honest readout, no invented words) gains without adding hardware risk.
- Escalation rule: the judge's "expected" row is 5.6 (< 6), but its J scores were already discounted for integration risk, so that row double-counts feasibility. We use the 7.0 weighted average and skip the extra lateral round (recorded in STATE.md).

## The entry
- Hearing wearer (teacher, classmate, desk staff) in **Meta Ray-Ban Display**. Deaf signer signs at 1–1.5 m. Lens shows the sentence + confidence; TTS plays through the glasses speaker. The signer holds/sees the **Signer Card** (web page on a tablet/phone): consent Start/Stop, "Translation ON", what the glasses said (glosses + sentence + confidence), ✓/✗, "Not right", Teach a sign, delete taught signs, captions of the wearer's spoken reply (or typed reply).
- **English only:** ASL → English text and speech. 24 visually distinct classroom ASL signs + REST.
  - Picked mainly from PopSign ASL v1.0's 250 signs (CC BY 4.0; the same sign list as Kaggle `asl-signs`, which we can't download without a Kaggle account).
  - Signs missing from it are recorded by the team or added with Teach.
  - FinSL is dropped from the plan.
  - See `research/webapps-and-datasets.md`.
- Confidence tiers: ≥0.80 show + speak; 0.50–0.80 amber "?" + top-2, nothing spoken until confirmed; < 0.50 "Didn't catch that".
- Not an interpreter: "Everyday phrases only. For medical, legal and exams, book an interpreter."

## Stack
Revision 2 (2026-11-13, after the lead's pointer to Meta's DAT iOS sample `samples/BirdSpotter`):
- **The glasses app is a native phone app on DAT 1.0.1, following BirdSpotter's structure.** BirdSpotter is Meta's reference "glasses app".
- It shows that one `DeviceSession` can hold the camera stream and the display at once, sending `FlexBox`/`Text` cards with `sendThroughActiveDisplay`.
  - This is inferred from its code: `activeCamera` + `activeDisplay` on the same session, and the display attaches once the stream reaches `.streaming`. M0 still confirms it on hardware.
- It plays TTS on the phone (`AVSpeechSynthesizer`), which reaches the glasses because they are the Bluetooth audio output.
- It needs no public tunnel, and caption text never leaves the local network, which is better for R3.

So:
- **Glasses + phone: "Signer" native app on DAT 1.0.1.** One session does three things:
  - **Camera:** streams to the core, `.raw` or `.hvc1` at medium 504x896 (BirdSpotter only used `.low` 7 fps, so the higher rate is M0's job to prove).
  - **Display:** DAT Display caption cards, 600×600. Each send replaces the screen, so sends are throttled.
  - **Speech:** phone TTS over Bluetooth to the glasses speaker.
  - It also has lifecycle/device-state UI and reply STT (phone mic; MWDATSpeech is experimental).
- **Copy BirdSpotter's structure:**
  - Repositories for session, camera, display and mock device.
  - An `AppContainer` that wires everything together.
  - A view-model that sends cards to the glasses only while the session is live.
  - Opt out of analytics in Info.plist.
- **Platform: iOS (Swift).** The lead confirmed a paid Apple developer team and an iPhone on iOS 17.2+ (2026-11-13). This avoids the reported free-Apple-ID "no frames" problem, matches the reference sample, and uses the lead's Mac + Xcode. Android is not built.
- **Without glasses:**
  - Mock Device Kit with `metaRayBanDisplay` (supported since DAT 1.0.0): an in-app preview, or an iOS Simulator build that streams the display to the Chrome "Meta Ray-Ban Display Simulator".
  - A mock camera fed from a video file (Android has `setCameraFeed(video)`; the iOS equivalent is checked in M0).
- **Web App = fallback and glasses-free demo surface.**
  - A 600×600 HTML page with WSS + `speechSynthesis`, installed by HTTPS URL / `fb-viewapp://` QR.
  - Used only if DAT Display can't run alongside the camera.
  - Also the quickest browser preview of the lens for the team (Display Simulator extension). Its HTTPS tunnel is only needed in that case.
- **Signer Core: Python on a team laptop** — FastAPI + WebSocket relay, MediaPipe Hands + Pose (+ Face blendshapes for the question flag), shoulder-normalised features + hand joint angles, segmenter, kNN/DTW baseline → small GRU if it wins on held-out signer, gloss→English (deterministic templates; Claude Haiku 4.5 fluent mode on gloss text only, with validator), eval harness (leave-one-signer-out). Deps: `mediapipe`, `opencv-python`, `fastapi`, `uvicorn`, `numpy`, `torch` (have), `anthropic`.
- **Signer Card: static web page** served by the core (QR to open).
- **Recognition data:**
  - No Kaggle account (lead, 2026-11-13), so Kaggle `asl-signs` is out.
  - **PopSign ASL v1.0** (CC BY 4.0, 47 signers): download only the 24 vocabulary signs, ~100 clips each (~2,400 clips), and run our own MediaPipe Holistic on them. Videos are deleted after extraction; only landmarks are kept. Extraction is split across the team's laptops. M0 finds out how the download works (whole archive vs per sign).
  - Then kNN prototypes from PopSign + our own recordings; GRU only if it wins on held-out signers.
  - ASL Citizen (non-commercial) as an optional held-out test on unseen Deaf signers.
- **Network:**
  - Phone ↔ laptop over **USB tethering**. The phone joins the glasses' Wi-Fi for streaming, so it can't also run a hotspot. Verified in M0.
  - The core sends captions back to the phone app over the same USB link; the phone renders them with DAT Display + TTS.
  - Only on the Web App fallback: a public HTTPS/WSS tunnel (cloudflared) carries caption text only, never frames.

## Data practice (R3)
Frames: glasses → phone → laptop over USB/LAN only, RAM only, dropped after landmark extraction, never written to disk, never sent to cloud. Only gloss text goes to Claude (fluent mode; off = deterministic). TTS/STT on-device. Logs: counts and latencies only. No face ID, no signer profile. Teach-mode prototypes stay on the laptop under a label; one-tap delete. Consent required before the camera session even opens; consent resets on STOPPED; auto-stop after 2 min idle; card Stop is the guaranteed path.

## R2 guardrail
The live demo uses the **glasses camera**. Webcam / phone camera are for development, data recording, eval and the backup video only. Fallback B (phone camera, labelled on stage) is a last resort, not the plan.

## Fallbacks (decided by end of M0)
- A: DAT Display can't run alongside the camera at the needed fps → captions go to the Signer Web App on the glasses (over WSS through the tunnel). The phone keeps the camera and TTS.
- B: no glasses frames (entitlement, freeze, no device) → phone back camera / webcam into the same core, captions still on glasses; labelled honestly.
- C: no Display device → Ray-Ban Meta Gen 2, audio-only TTS.

## Non-code deliverables
Deck (8–10 slides, incl. honest eval chart, "What we are not", consent design, pilot), 60–90 s demo video (doubles as backup), live-demo kit (printed consent sign, volunteer consent form, scripted phrase sequence, QR), pilot one-pager draft (no partner claimed).

## Cut list (first → last)
1. Claude fluent mode (keep templates) 2. question flag 3. GRU (ship kNN) 4. Teach-a-sign (cut at Sat 18:00 if M2 is late) 5. reply STT (typed reply instead) 6. on-phone MediaPipe stretch.
**Never cut:** consent/Start-Stop, confidence tiers, wearer reply → card captions (typed at minimum), the 3 triggerable D3 states (permission denied, glasses off, core down), held-out eval number, backup video.
**Dropped entirely:** Neural Band input, negation flag, fingerspelling, Gemini verifier, sign-based consent.

## Scope changes
- 2026-11-13 (lead): M0's spike results (D1, D2) and iOS build (D4) moved to a separate contract `contracts/M0-hw.json`, run in glasses slot G1 after the Xcode ≥ 26.4 update. M0 is done on the software checks (D3, D5–D11, incl. the real webcam bench D8). The fallback decision still has to land in M0-hw before M2 starts.
