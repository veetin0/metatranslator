# Option: Safe winner: "Signer: Class Bridge"

## 1. Concept
- **Pitch:** A hearing teacher or classmate in Meta Ray-Ban Display glasses understands the 24 classroom signs a deaf pupil uses most, shown as captions in the lens and spoken aloud. The pupil sees and controls everything on a "Signer Card" facing them.
- **Audience:** hearing teachers, classmates and service-desk staff who don't sign, plus the deaf signers who meet them in unbooked everyday moments (corridor, group work, the desk). Interpreters are booked, scarce and rationed by Kela (prior-art §2). This tool fills the ad-hoc gap and does not replace them.
- **Scenario:** at the classroom door the pupil signs HELLO / QUESTION / HOMEWORK WHERE. The teacher reads "Hi. I have a question: where is the homework?" in the lens, hears it, and answers by voice. The answer appears as text on the Signer Card.
- **Why first-person (R2):** the camera sees what the wearer is looking at, so the wearer keeps eye contact with the signer, both hands stay free (a teacher holding books, chalk or a door), and no phone is pointed at the deaf person. The caption sits in the wearer's line of sight, so they never look down. A phone version would break eye contact and feel like filming someone.

## 2. Architecture (thin phone, local core)
```
Ray-Ban Display ──DAT camera 504x896@15fps──▶ Android app (Kotlin, DAT 1.0.1)
      ▲  DAT Display: caption + state           │ JPEG frames @10fps over phone hotspot (LAN only)
      │  TTS (Android, on-device) → BT speaker  ▼
      └──────── caption JSON ◀──── Signer Core (Python, team laptop, FastAPI+WebSocket)
                                     MediaPipe Hands+Pose(+Face blendshapes) → segmenter → kNN/GRU classifier
                                     → gloss→English (deterministic table; Claude Haiku "fluent mode" on gloss TEXT only)
                                     ├─▶ Signer Card web page (tablet/phone facing signer): consent, ON light, captions, "Not right"
                                     └─▶ Webcam source (fallback; same pipeline)
```
- **Platform: Android DAT (Kotlin)** as primary. The paid Apple team is unconfirmed, and a free-ID iOS build gets BLE but no frames (platform §3.5). iOS is used only if a paid team is confirmed in hour 0 *and* Android fails the spike. One platform only.
- **Why the core runs on the laptop:** the same Python code serves the glasses source, the webcam fallback and the eval harness, so there is one feature pipeline and no train/serve mismatch. The phone stays a thin bridge: camera in, display and TTS out, state machine. Stretch goal: move MediaPipe onto the phone so only landmarks leave it.
- **What leaves which device (R3):** frames go phone → laptop over the phone's own hotspot. The venue Wi-Fi and the cloud never see them, they are held in RAM and dropped after landmark extraction, and nothing is written to disk. Only gloss text (e.g. "HOMEWORK WHERE ?") goes to Claude, and only in fluent mode. TTS and STT run on-device. Logs keep counts and latencies, with no content. No face ID and no signer profile (AUP + GDPR Art. 9).
- **Camera + display in the same session (the #1 risk), decided in the spike:**
  - Fallback A: captions move to a **glasses Web App** (static HTML, WebSocket to Signer Core), which runs separately from the DAT session; the phone keeps camera + TTS.
  - Fallback B: no glasses camera frames (entitlement, freeze, no device): the phone's back camera on a chest lanyard feeds the same core, captions stay on the glasses, and the demo labels the source honestly as "camera: phone".
  - Fallback C: no Display device: Ray-Ban Meta Gen 2, audio-only TTS.

## 3. Recognition
- **Vocabulary: 24 isolated ASL signs plus a REST class**, picked to look clearly different from each other: HELLO, THANK-YOU, PLEASE, SORRY, YES, NO, HELP, QUESTION, UNDERSTAND, NOT-UNDERSTAND, AGAIN, SLOW, WAIT, FINISH, WHERE, WHAT, NAME, HOMEWORK, BOOK, TEACHER, BATHROOM, WATER, BREAK, GOOD. Fingerspelling is cut. Signs are learned from a video dictionary; the deck says we are not fluent signers.
- **Pipeline:** MediaPipe landmarks → normalise to shoulder width and body centre, plus hand joint angles (robust to head motion) → segment by hands rising above and returning to rest → classify the window. kNN/DTW is the baseline (hour 6); a small GRU on landmark sequences runs on CPU in seconds. Non-manual marker: raised eyebrows mark the sentence as a question ("?"). It is shown as a tag, never claimed as translation.
- **Data:** 3–4 team signers × 20 clips × 25 classes, recorded with a webcam tool, plus 5 clips per sign through the **glasses camera** to measure domain shift. We also try to recruit one volunteer signer at Junction (written consent) as a truly unseen test signer.
- **Metric (the hackforge:eval harness):** leave-one-signer-out top-1 and top-3, **selective accuracy at the operating threshold plus abstain rate**, and the same numbers on the glasses-camera clips. Target: ≥85% selective accuracy at ≤25% abstain on a held-out signer. We report whatever we actually measure. Latency is timed from sign end to caption (target <1.5 s, shown live on the phone).
- **Confidence on the lens:** ≥0.80 → caption + TTS. 0.50–0.80 → "HELP?" in amber; nothing is spoken until the wearer taps the touchpad or the signer confirms. <0.50 → "…" with no output. The top-2 candidates show on the Signer Card.

## 4. D3 handling (every case is visible in the UI; the demo includes a 20 s "failure tour" of 3 of them)
| Case | Behaviour |
|---|---|
| Camera permission denied in the Meta AI app | Lens + phone: "Camera not allowed. Tap to open Meta AI." Deep link opens the request again. Recognition stays off. |
| Phone mic permission denied | The reply path is turned off and the Signer Card says "Speech captions unavailable". Recognition keeps working. |
| DAT registration / version too old | Phone shows the required Meta AI app and firmware versions (V292/V128) with steps. |
| Session PAUSED (touch, system UI) | Lens: "Paused". Frames stop. We wait and don't restart while PAUSED, per DAT lifecycle rules. |
| Session STOPPED (hinge fold, glasses taken off, BT loss) | Recognition and consent end automatically. The Signer Card turns grey ("Stopped: glasses off"). A new session needs fresh consent. |
| Thermal level high / battery low | Drop to 360x640 @7 fps and show a "power-save" badge. Below 10% battery, a warning goes to both screens. |
| Display interrupted (call or notification) | Re-send the last caption view when the display comes back. Captions are never lost because the phone is the source of truth. |
| Laptop core unreachable | Lens: "Offline: not translating". Auto-reconnect with backoff. Frames are never queued, to avoid a burst of stale captions. |
| Internet lost (LLM) | Silent fallback to deterministic gloss phrasing, with a small "basic mode" tag. |
| Signer out of frame / hands not visible | Lens hint: "Step back: hands not visible", based on pose detection. |
| Signer withdraws consent | Stop button or "Not now" on the card: the stream stops within 1 s, the camera LED goes off and the lens shows "Signer paused translation". |
| Low confidence | Amber "?" state, as in §3. No guesses are spoken. |
| Performance trade-off | Stream at `.medium`/15 fps (less compression, per Meta), process at 10 fps. Latency and fps show on the phone debug strip. |

## 5. Signer-side UX and consent (I1, J4)
- **Signer Card** (web page on a tablet or phone facing the signer, large type, high contrast):
  1. Consent screen in plain language plus a short sign video: what the glasses do, that nothing is recorded and that captions are not stored. "Start" / "Not now".
  2. A large **"Translation ON"** light while recognition runs.
  3. **"What the glasses said"**: every caption the wearer saw or heard, with its confidence.
  4. **"Not right"** button: removes the caption from the lens and makes the wearer's lens show "Signer says: not that".
  5. **Reply captions**: the wearer's speech, transcribed on-device.
  6. Stop at any time.
- The wearer cannot start recognition without the Signer Card's consent. Consent covers only one session and ends with it.
- Shown on screen: "Everyday phrases only. For medical, legal and exams, book an interpreter."

## 6. Milestones (each one ends in a demo; hours count from the start; freeze at h30, buffer h30–34)
| M | Hours | Slice (demoable) | Owners |
|---|---|---|---|
| M0 | 0–2 | **Go/no-go spike on hardware.** Update the Meta AI app and firmware, Dev Mode, register the Android sample. Pass = (a) frames from the glasses camera on the phone, (b) "Hello" on the Display **while** the stream runs, (c) TTS audible in the glasses, (d) a glasses Web App hello via the simulator and the device. In parallel: webcam MediaPipe landmarks at ≥15 fps; the vocabulary is frozen and the recording tool works. | P1 (a,b,c), P2 (d + paid Apple team check), P3 landmarks, P4 vocab/record tool |
| M1 | 2–10 | **Webcam end-to-end:** webcam → core → 24-sign kNN → caption in a 600x600 glasses-style browser view + TTS. All clips recorded; eval v0 (LOSO). | P3 core+model, P4 data+eval, P1 DAT bridge, P2 caption UI (DAT or Web App, per M0) |
| M2 | 10–18 | **On the glasses:** DAT stream → core → caption on the Display + TTS in the glasses speaker. Confidence tiers; state machine for permission, session and device events. | P1 phone, P2 lens UI, P3 GRU + segmenter tuning, P4 glasses-camera clips + eval |
| M3 | 18–26 | **Two-way + trust:** Signer Card (consent, ON light, captions, Not right, reply STT), every D3 case in §4, LLM fluent mode with offline fallback, question flag. | P2 Signer Card, P1 D3 cases + STT, P3 LLM/question flag, P4 deck v1 |
| M4 | 26–30 | **Demo-proof:** final held-out eval, a 60–90 s demo video recorded from the working build, deck final, 3 timed rehearsals on the real device, failure tour, backup clip. | P4 deck/video, P3 eval slide, P1+P2 rehearsal + bug fixes |

Sleep: two 3-hour shifts (P1+P3 during h12–15, P2+P4 during h15–18), so someone is always on the critical path.

## 7. Non-code deliverables and pilot (D2, D4, D5)
- **Deck (8 slides):** problem and audience (3,000–5,000 deaf FinSL signers, rationed interpreters, cited as a range); scenario; live demo; architecture and the "what leaves the device" diagram; honest eval (held-out signer, abstain rate, glasses-camera domain shift); "What we are not" (not an interpreter replacement; we answer the WFD/efsli concerns); consent design; pilot.
- **Demo video, 60–90 s:** POV screen capture plus real footage of the door scenario, consent and the two-way reply. It doubles as a backup if the live demo fails.
- **Demo kit:** printed table sign ("Camera in use for sign recognition demo, nothing recorded"), a written consent form for the volunteer signer, the rehearsed script, and a pre-charged spare phone.
- **Pilot path:** co-design with Kuurojen Liitto comes first (we claim no endorsement). Then one Helsinki-area school or a university accessibility desk, 4 weeks, ~50 class and desk phrases **re-recorded in FinSL** by deaf signers who own that data. Measures: comprehension rate, signer-rated "accurate/respectful" score, and minutes saved per interaction. This works because the few-shot pipeline doesn't depend on the language: switching to FinSL means re-recording, not new research.

## 8. Risks, mitigations, cut list
| Risk | Mitigation |
|---|---|
| Camera and display can't share a DAT session | Fallback A (glasses Web App captions), decided by h2 |
| No Android phone that works with DAT / device shortage | iOS only if a paid team exists; otherwise Fallback B (phone camera). Reserve a device for judging (Q3) |
| Accuracy collapses on the glasses camera (blur, 60–100 px hands) | Medium preset at 15 fps, crop around the signer using pose, "sign in front of chest at 1–1.5 m" hint, glasses clips in training, threshold + abstain |
| Held-out signer accuracy is low | Report it honestly; the per-signer calibration step (5 clips) is shown as a pilot feature; keep the vocabulary at 24 |
| Venue Wi-Fi is bad | Phone hotspot LAN; the LLM is optional; TTS and STT run on-device |
| Glasses overheat or the stream freezes (HEVC bug) | Use `.raw` frames, stream only while the card is ON, short demo bursts, spare device |
| Demo nerves or a bad sign on stage | Rehearse 3×, use a fixed phrase script, keep the backup video ready |

**Cut first → last:** (1) the Claude fluent mode, (2) the question flag, (3) the GRU (ship kNN), (4) reply STT (type the reply on the card instead), (5) the on-phone MediaPipe stretch. **Never cut:** consent card, confidence tiers, the D3 states shown, the held-out eval number, the backup video.

## 9. Self-score
| J | Score | Why |
|---|---|---|
| J1 Creativity/use case | 7 | Reverses caption glasses (the hearing wearer understands the signer) in a concrete classroom moment. Sign translation itself is a familiar idea. |
| J2 Technical execution | 8 | A real DAT camera → ML → Display + TTS loop on the device, a documented lifecycle and D3 handling, a measured eval. The bounded vocabulary caps the wow factor. |
| J3 Real-world value/feasibility | 7 | Fills the ad-hoc interpreter gap, with a credible FinSL pilot and a design that responds to the deaf community. 24 signs is clearly a prototype. |
| J4 UX: input/accessibility/trust | 9 | The signer controls consent and corrections and sees every output, nothing is spoken below the threshold, data rules are explicit, and the experience is two-way. |
