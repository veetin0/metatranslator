# Decision

**Build "Signer: Class Bridge" (option A) as the spine, with three grafts from Signer Duet: Teach-a-sign, the live ✓/✗ accuracy readout, and the gloss-only LLM validator.**

## Why
- Same weighted judge score as Duet (7.0) at much higher feasibility (8 vs 5.5); Duet's own M1 is effectively A.
- The grafts are the cheapest J1 (Teach = memorable stage moment + FinSL pilot story) and J4 (honest readout, no invented words) gains without adding hardware risk.
- Escalation rule: the judge's "expected" row is 5.6 (< 6), but its J scores were already discounted for integration risk, so that row double-counts feasibility. We use the 7.0 weighted average and skip the extra lateral round (recorded in STATE.md).

## The entry
- Hearing wearer (teacher, classmate, desk staff) in **Meta Ray-Ban Display**. Deaf signer signs at 1–1.5 m. Lens shows the sentence + confidence; TTS plays through the glasses speaker. The signer holds/sees the **Signer Card** (web page on a tablet/phone): consent Start/Stop, "Translation ON", what the glasses said (glosses + sentence + confidence), ✓/✗, "Not right", Teach a sign, delete taught signs, captions of the wearer's spoken reply (or typed reply).
- 24 visually distinct classroom ASL signs + REST. FinSL is the pilot roadmap (re-record / Teach by deaf signers).
- Confidence tiers: ≥0.80 show + speak; 0.50–0.80 amber "?" + top-2, nothing spoken until confirmed; < 0.50 "Didn't catch that".
- Not an interpreter: "Everyday phrases only. For medical, legal and exams, book an interpreter."

## Stack
- **Phone: native Android Kotlin app on DAT 1.0.1** (camera stream `.medium` 504x896 @15 fps, DAT Display captions, Android on-device TTS → glasses speaker, Android offline SpeechRecognizer with phone mic, lifecycle/device-state UI). iOS Swift only if a paid Apple team is confirmed *and* Android fails M0. If neither works → Fallback B (see below), which weakens R2.
- **Signer Core: Python on a team laptop** — FastAPI + WebSocket relay, MediaPipe Hands + Pose (+ Face blendshapes for the question flag), shoulder-normalised features + hand joint angles, segmenter, kNN/DTW baseline → small GRU if it wins on held-out signer, gloss→English (deterministic templates; Claude Haiku 4.5 fluent mode on gloss text only, with validator), eval harness (leave-one-signer-out). Deps: `mediapipe`, `opencv-python`, `fastapi`, `uvicorn`, `numpy`, `torch` (have), `anthropic`.
- **Signer Card: static web page** served by the core (QR to open).
- **HUD fallback: glasses Web App** (600x600 HTML, WebSocket to core) if camera + DAT Display can't share a session.
- **Network:** the glasses host Wi-Fi for streaming and the phone joins it, so the phone **cannot** also serve a hotspot. Phone ↔ laptop goes over **USB tethering** (or a laptop-hosted hotspot); verified in M0.

## Data practice (R3)
Frames: glasses → phone → laptop over USB/LAN only, RAM only, dropped after landmark extraction, never written to disk, never sent to cloud. Only gloss text goes to Claude (fluent mode; off = deterministic). TTS/STT on-device. Logs: counts and latencies only. No face ID, no signer profile. Teach-mode prototypes stay on the laptop under a label; one-tap delete. Consent required before the camera session even opens; consent resets on STOPPED; auto-stop after 2 min idle; card Stop is the guaranteed path.

## R2 guardrail
The live demo uses the **glasses camera**. Webcam / phone camera are for development, data recording, eval and the backup video only. Fallback B (phone camera, labelled on stage) is a last resort, not the plan.

## Fallbacks (decided by end of M0)
- A: camera + DAT Display can't coexist → captions in the glasses Web App; phone keeps camera + TTS.
- B: no glasses frames (entitlement, freeze, no device) → phone back camera / webcam into the same core, captions still on glasses; labelled honestly.
- C: no Display device → Ray-Ban Meta Gen 2, audio-only TTS.

## Non-code deliverables
Deck (8–10 slides, incl. honest eval chart, "What we are not", consent design, pilot), 60–90 s demo video (doubles as backup), live-demo kit (printed consent sign, volunteer consent form, scripted phrase sequence, QR), pilot one-pager draft (no partner claimed).

## Cut list (first → last)
1. Claude fluent mode (keep templates) 2. question flag 3. GRU (ship kNN) 4. Teach-a-sign (cut at Sat 18:00 if M2 is late) 5. reply STT (typed reply instead) 6. on-phone MediaPipe stretch.
**Never cut:** consent/Start-Stop, confidence tiers, wearer reply → card captions (typed at minimum), the 3 triggerable D3 states (permission denied, glasses off, core down), held-out eval number, backup video.
**Dropped entirely:** Neural Band input, negation flag, fingerspelling, Gemini verifier, sign-based consent.
