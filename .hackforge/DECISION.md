# Decision

**Build "Signer: Class Bridge" (option A) as the spine, with three grafts from Signer Duet: Teach-a-sign, the live ✓/✗ accuracy readout, and the gloss-only LLM validator.**

## Why
- Same weighted judge score as Duet (7.0) at much higher feasibility (8 vs 5.5); Duet's own M1 is effectively A.
- The grafts are the cheapest J1 (Teach = memorable stage moment + FinSL pilot story) and J4 (honest readout, no invented words) gains without adding hardware risk.
- Escalation rule: the judge's "expected" row is 5.6 (< 6), but its J scores were already discounted for integration risk, so that row double-counts feasibility. We use the 7.0 weighted average and skip the extra lateral round (recorded in STATE.md).

## The entry
- Hearing wearer (teacher, classmate, desk staff) in **Meta Ray-Ban Display**. Deaf signer signs at 1–1.5 m. Lens shows the sentence + confidence; TTS plays through the glasses speaker. The signer holds/sees the **Signer Card** (web page on a tablet/phone): consent Start/Stop, "Translation ON", what the glasses said (glosses + sentence + confidence), ✓/✗, "Not right", Teach a sign, delete taught signs, captions of the wearer's spoken reply (or typed reply).
- **English only:** ASL → English text and speech. 24 visually distinct classroom ASL signs + REST.
  - Picked mainly from the 250 signs of the Google Isolated Sign Language dataset (Kaggle `asl-signs`, MediaPipe landmarks).
  - Signs missing from it are recorded by the team or added with Teach.
  - FinSL is dropped from the plan.
  - See `research/webapps-and-datasets.md`.
- Confidence tiers: ≥0.80 show + speak; 0.50–0.80 amber "?" + top-2, nothing spoken until confirmed; < 0.50 "Didn't catch that".
- Not an interpreter: "Everyday phrases only. For medical, legal and exams, book an interpreter."

## Stack
Changed 2026-11-13 by the lead after reading Meta's docs: the lens UI is a **Web App**, which can be developed without glasses in Meta's simulator.

- **Glasses: "Signer" Web App = the lens HUD.** The real app on the glasses.
  - A 600×600 HTML/JS page (Meta's starter kit + UI Toolkit, or plain HTML if it fits the < 300 KB budget).
  - It receives captions over WSS from the core and speaks them with `speechSynthesis`, which plays through the glasses speaker.
  - It is served on a public HTTPS URL and installed in the Meta AI app in Developer Mode (Connect Web App, or the `fb-viewapp://` QR).
  - It is developed and QA'd in the Meta Ray-Ban Display Simulator Chrome extension, with a webcam background, so most of the team never needs glasses.
- **Phone: thin Android Kotlin app on DAT 1.0.1, camera only.**
  - Streams the camera at `.medium` 504x896 @15 fps to the core, plus lifecycle/device-state UI and reply STT (phone mic).
  - Web Apps get no camera, so DAT is still the only path for camera frames.
  - Mock Device Kit `setCameraFeed(video)` lets us test it without glasses.
  - **DAT Display captions are now the fallback**, used if the Web App can't stay open while DAT streams, or if its latency is bad.
  - iOS only if a paid Apple team is confirmed *and* Android fails M0. If neither works → Fallback B, which weakens R2.
- **Signer Core: Python on a team laptop** — FastAPI + WebSocket relay, MediaPipe Hands + Pose (+ Face blendshapes for the question flag), shoulder-normalised features + hand joint angles, segmenter, kNN/DTW baseline → small GRU if it wins on held-out signer, gloss→English (deterministic templates; Claude Haiku 4.5 fluent mode on gloss text only, with validator), eval harness (leave-one-signer-out). Deps: `mediapipe`, `opencv-python`, `fastapi`, `uvicorn`, `numpy`, `torch` (have), `anthropic`.
- **Signer Card: static web page** served by the core (QR to open).
- **Recognition data:**
  - Pretrain on Kaggle `asl-signs`: ~94k clips, 250 signs, landmarks already extracted. The licence must be confirmed in M0; PopSign v1.0 is CC BY 4.0 as backup.
  - Then use kNN/fine-tuning on our own recordings.
  - ASL Citizen (non-commercial) as an optional held-out test on unseen Deaf signers.
- **Network:**
  - Phone ↔ laptop over **USB tethering**. The phone joins the glasses' Wi-Fi for streaming, so it can't also run a hotspot. Verified in M0.
  - The Web App reaches the core through a **public HTTPS/WSS tunnel** (cloudflared) to the laptop. Only caption text and confidence go through the tunnel; frames never do.
  - The static Web App can also sit on Vercel/GitHub Pages and open a WSS connection to the tunnel.

## Data practice (R3)
Frames: glasses → phone → laptop over USB/LAN only, RAM only, dropped after landmark extraction, never written to disk, never sent to cloud. Only gloss text goes to Claude (fluent mode; off = deterministic). TTS/STT on-device. Logs: counts and latencies only. No face ID, no signer profile. Teach-mode prototypes stay on the laptop under a label; one-tap delete. Consent required before the camera session even opens; consent resets on STOPPED; auto-stop after 2 min idle; card Stop is the guaranteed path.

## R2 guardrail
The live demo uses the **glasses camera**. Webcam / phone camera are for development, data recording, eval and the backup video only. Fallback B (phone camera, labelled on stage) is a last resort, not the plan.

## Fallbacks (decided by end of M0)
- A:
  - **If the Web App can't run while DAT streams, or the tunnel is too slow:** captions move to DAT Display, rendered by the phone app, and TTS moves to Android TTS.
  - **If neither display works alongside the camera:** the Web App runs on its own for display and TTS, and the camera comes from Fallback B.
- B: no glasses frames (entitlement, freeze, no device) → phone back camera / webcam into the same core, captions still on glasses; labelled honestly.
- C: no Display device → Ray-Ban Meta Gen 2, audio-only TTS.

## Non-code deliverables
Deck (8–10 slides, incl. honest eval chart, "What we are not", consent design, pilot), 60–90 s demo video (doubles as backup), live-demo kit (printed consent sign, volunteer consent form, scripted phrase sequence, QR), pilot one-pager draft (no partner claimed).

## Cut list (first → last)
1. Claude fluent mode (keep templates) 2. question flag 3. GRU (ship kNN) 4. Teach-a-sign (cut at Sat 18:00 if M2 is late) 5. reply STT (typed reply instead) 6. on-phone MediaPipe stretch.
**Never cut:** consent/Start-Stop, confidence tiers, wearer reply → card captions (typed at minimum), the 3 triggerable D3 states (permission denied, glasses off, core down), held-out eval number, backup video.
**Dropped entirely:** Neural Band input, negation flag, fingerspelling, Gemini verifier, sign-based consent.
