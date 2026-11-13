# Option: AMBITIOUS: "Signer Duet": a two-way conversation loop through Ray-Ban Display

## 1. Concept
- **Pitch:** The hearing person wears Ray-Ban Display. A deaf person signs to them and the lens shows a full sentence, which is also spoken aloud. The wearer answers by speaking, and the signer reads the answer live on their own "Duet card". Each side can confirm or correct the other, and a deaf user can teach it a new sign in 30 seconds.
- **Audience:** hearing non-signers who meet deaf signers in unbooked, everyday moments: a teacher or classmate in school (primary), and front-desk staff. The deaf signer is a co-user, not a subject.
- **Scenario ("classroom door"):** A deaf pupil comes to the teacher after class. They sign "TOMORROW TEST WHERE?" with raised brows. The teacher's lens shows *"Where is the test tomorrow?"* and the phone says it aloud through the glasses speaker. The teacher replies "Room 204, at nine." The pupil's Duet card shows it as large captions. The pupil spells a classmate's name (stretch) and taps ✓ on the card. Nobody had to book an interpreter for a 40-second chat.
- **Why first-person view beats a phone (R2):** the camera already points where the wearer looks, so nobody holds a phone between the two people. Eye contact and facial grammar stay visible to both: brows and headshake carry meaning in sign language, and a phone held up blocks the face. Both of the wearer's hands stay free, which matters for a teacher holding papers. The caption sits in the wearer's line of sight, so they keep looking at the signer and not down at a screen. A phone can only be a mirror; here the glasses are the sensor, the display and the speaker.

## 2. Architecture
**Platform path:** a native **Android (Kotlin) DAT app** is primary, because the paid Apple team is not confirmed and a free Apple ID never receives camera frames. iOS Swift only if a paid team is confirmed in hour 0 (same design). The glasses HUD uses **DAT Display**, with a fallback to a **glasses Web App** subscribed to the relay.

```
Ray-Ban Display ──DAT camera 504x896@15fps──▶ Android "Signer" app ──frames over local Wi-Fi (RAM only)──▶ Edge relay (team laptop, Python)
   ▲  HUD text + status (DAT Display)            │ on-device STT (wearer speech)          │ MediaPipe Holistic → landmarks; frames dropped
   │  TTS audio (BT to glasses speaker)          │ Neural Band events (experimental)      │ segmenter → classifier (kNN+GRU) → gloss + conf
   └────────────────────────────────────────────┘                                        │ NMM flags (brows/headshake) → sentence assembler
                                                                                         │   (Claude Haiku-class: glosses+flags+context TEXT ONLY;
Duet card (signer's phone/tablet web page) ◀──WebSocket── relay state ──────────────────▶│    offline fallback = rule template)
   consent, live "what glasses think", ✓/✗, captions of wearer speech, Teach mode        └─▶ events → phone app (HUD + TTS) and Duet card
Webcam source (laptop/browser) ──same frame interface──▶ relay   (fallback B, and for Teach/recording)
```
- **Components:** (1) Android DAT app: registration and permissions, camera session, HUD renderer, TTS, STT, device-state UI. (2) Edge relay: FastAPI + WebSocket, MediaPipe, recognizer, LLM assembler, session and consent state machine. (3) Duet card: a static web page served by the relay and opened by QR code. (4) Glasses Web App: a fallback HUD (600x600 HTML, WebSocket).
- **Where ML runs:** landmarks, the classifier and NMM all run on the laptop on the local network. Nothing visual goes to the cloud. Only the LLM call is in the cloud, and it gets gloss tokens, flags and the last 3 caption lines as text.
- **What leaves the device (R3):** glasses→phone goes over the DAT link. Phone→laptop sends raw frames over the team's own local network; they are held in RAM only and discarded after landmarks are extracted, and no frame is ever written to disk. Laptop→cloud sends gloss text only. Wearer speech is transcribed on-device by Android SpeechRecognizer in offline mode, with the phone mic or the DAT 8 kHz mic. Teach-mode landmark templates stay on the laptop under the signer's name label, and the signer can delete them with one button. There is no face ID and no signer identification (Meta AUP).
- **Camera and display in the same session (the #1 risk):** the spike tests this first. If DAT Display cannot run during a camera session, the HUD moves to the **glasses Web App**, a separate runtime with no session conflict, fed by the relay WebSocket. If the Web App cannot play audio, TTS stays on the phone and routes over Bluetooth. If the glasses camera fails entirely (no frames, freezes, no device available), the input is the phone's back camera or the laptop webcam through the same frame interface. The captions still go to the glasses, and the demo labels the camera source honestly.

## 3. Recognition
- **Vocabulary:** **40 signs** (ASL), chosen to be visually distinct: about 25 classroom signs (TEST, TOMORROW, WHERE, HOMEWORK, HELP, UNDERSTAND, REPEAT, SLOW, TEACHER, BATHROOM, …) and 15 everyday or conversational ones (YES, NO, THANK-YOU, PLEASE, NAME, WHAT, WHEN, FINISH, …). Two non-manual flags: **question** (brows raised + head tilt) and **negation** (headshake from the yaw oscillation of the face transform). **Stretch:** static fingerspelling (~20 letters) for names. **Core:** Teach mode adds any new sign live.
- **Pipeline:** MediaPipe Holistic gives hands, 8 upper-body pose points and face blendshapes. Features are normalised to the shoulders (this cancels the wearer's head motion) and include hand joint angles. Utterances are segmented by hands rising into and dropping out of the signing space, plus a motion-energy pause. The baseline is kNN with DTW. A small GRU trained on the laptop CPU in seconds is used if it beats kNN on the held-out signer. The output is a gloss stream with a softmax/distance confidence.
- **Sentence assembly:** Claude Haiku-class runs with a "mode" context (Classroom / Front desk) and the last turns of both sides. It must return JSON `{sentence, glosses_used}`, and a validator rejects any sentence that adds content words not in the glosses. The raw glosses are always shown under the sentence on the Duet card. If the LLM is offline or slow (>1.5 s), the rule template is used and labelled "simple phrasing".
- **Teach-a-sign (headline feature):** the signer taps "Teach", types or picks a label, and signs it 5 times. These become kNN prototypes and the sign works in about 30 s. This is language-agnostic, so it gives the **FinSL pilot story**: deaf users build their own vocabulary and own that data.
- **Gemini closed-set verifier:** *stretch, opt-in, off by default.* It runs only when top-1 is below 0.6. It sends a 2 s clip plus the top-5 candidate list, and the Duet card shows a "cloud check ON" banner when it is enabled. It is cut first.
- **Measurement:** recorded clips are 4 team signers × 20 per sign. The headline number is **leave-one-signer-out** accuracy, not random-split accuracy, plus one non-team volunteer if we find one. We report top-1, top-3, the abstain rate at the threshold, and a reliability chart (eval script plus a run log). Target: ≥85% on a seen signer, ≥70% on the held-out signer. We publish whatever we actually get.
- **Confidence in the UI:** three tiers. **≥0.8** is spoken automatically. **0.5–0.8** shows "?" with the top-2 and waits for a ✓ from the wearer (Neural Band pinch) or the signer (card). **<0.5** shows "Didn't catch that, please repeat" and nothing is spoken. An **honest live accuracy readout** sits in the HUD footer and on the card ("session: 17/19 confirmed"), counted from the signer's ✓/✗ taps.

## 4. D3 cases the prototype visibly handles (each shown in a 20 s "failure tour" in the demo)
| Case | Trigger | Visible behaviour |
|---|---|---|
| Camera permission denied or "once" expired | Meta AI permission sheet | App screen "Camera access needed" with a deeplink retry. The HUD shows "Camera off". The Duet card shows OFF. |
| Mic or STT permission denied | Android dialog | The reply path switches to "type reply" on the phone, and the card says "Wearer is typing". |
| DAT registration missing or app switched | `registrationStateStream` | A setup checklist screen. The session cannot start. |
| Session PAUSED (system UI, a call) | `DeviceSessionState.PAUSED` | The HUD shows "Paused", recognition is held, and nothing is re-started while paused. |
| Session STOPPED (hinge folded, glasses taken off, link lost) | STOPPED or don/doff | Recognition auto-stops, **consent resets**, buffers are purged, and the card shows "Glasses off". Restarting starts a new session. |
| Low battery or thermal level high | device state | Drop to 7 fps / `.low` and show the chip "Cooling, slower". A warning appears at the battery threshold. |
| Link bandwidth drop | SDK degrades res/fps | An fps/latency chip appears. Below 10 fps the HUD shows "Link slow, sign slower". |
| Relay unreachable | WS close | "Reconnecting…" with backoff. After 10 s the app offers the webcam fallback. |
| LLM timeout or no internet | >1.5 s or error | Template phrasing tagged "simple phrasing". Recognition keeps working, because everything except the LLM runs on the local network. |
| Signer out of frame or no hands visible | pose missing | The HUD hint "Face the signer, step back". No guesses are made. |
| Consent withdrawn | card STOP or the agreed "stop" sign | Immediate stop, purge, and a red OFF on both sides. |
| **Performance trade-off** | design | Streaming runs only while consent is ON. The settings are 15 fps / `.medium`. The LLM is called once per utterance, not per frame. The HUD is updated only on a state change, because DAT sends the whole view each time. The measured end-to-end latency is shown in the debug chip. |

## 5. Inclusive, two-way UX and consent
- **Duet card (the signer's own screen):** the signer opens it on their own phone, or on a tablet on the desk, by scanning a QR code on the wearer's phone. It is in large type and dark mode. It shows **Consent** (Start / Stop), "Glasses ON / OFF", live **what the glasses think** (glosses + sentence + confidence), **✓ / ✗ / Repeat**, **Teach a sign**, **captions of the wearer's speech** (big, scrolling), "delete my taught signs", and the plain-language privacy note: *"Video stays on this table's laptop and is deleted instantly. Only words go online. Not an interpreter: for medical, legal or exams, book one."*
- **Consent flow:** (1) the wearer's HUD shows "Ask to start". (2) The signer taps Start on the card, or signs the agreed START sign once it is recognised. (3) Both sides show ON and the camera LED is lit. (4) Auto-stop after 2 min idle, when the glasses come off, or on STOP. No consent means no streaming: the camera session is not even opened.
- **Wearer input:** Neural Band pinch = confirm / speak, swipe = ask to repeat (*stretch*, because the inputs API is experimental). The fallback is phone buttons. The HUD is 600x600, bright on black, with one sentence in heading text, a confidence chip, and a status line.
- **Language honesty:** the demo is in ASL with a bounded vocabulary, and the size of the vocabulary is shown on the card. FinSL is the pilot plan through Teach mode. We do not claim any deaf endorsement or co-design.

## 6. Milestones (4 people: **A** Android/DAT, **B** recognition/ML, **C** relay + LLM + Duet card, **D** HUD Web App + data, eval, deck and video)
| # | Hours | Slice (each one can be demoed) | Owners |
|---|---|---|---|
| M0 | 0–2 | **Go/no-go spike on hardware:** firmware / Meta AI app versions, Dev Mode, register the Android app, (1) a frame on the phone, (2) "Hello" on the HUD **while streaming**, (3) TTS in the glasses speaker, (4) measured latency and a 10 min thermal check. In parallel: B builds the webcam MediaPipe + kNN on 5 signs, C writes the relay skeleton and frame contract, D writes the Web App HUD in the simulator and the vocabulary list. **Decide:** DAT Display or Web App HUD; glasses camera or webcam source. | A (B, C, D in parallel) |
| M1 | 2–12 | **Safe core, one-way:** glasses (or webcam) → relay → 40-sign kNN → template sentence → HUD + TTS, with the three confidence tiers and the consent Start/Stop on a minimal Duet card. Record 4 signers × 20 clips. **This is the fallback that must always work.** | A app + HUD, B recognizer + recording, C relay + card, D data + eval script |
| M2 | 12–20 | **Two-way + trust:** wearer STT → card captions; LLM assembler with the validator and mode context; ✓/✗ and the live accuracy readout; all D3 states wired; held-out-signer eval v1; GRU if it wins. | A STT + states, B GRU + eval, C LLM + card, D HUD states + deck draft |
| M3 | 20–27 | **Wow layer (stretch, time-boxed):** Teach-a-sign (core-stretch, done first), NMM question/negation flags, Neural Band confirm, fingerspelling for names, Gemini verifier (last). Each one sits behind a flag, so cutting it costs nothing. | B Teach + NMM, A Neural Band, C fingerspelling/verifier, D UX polish |
| M4 | 27–33 | **Harden + pitch:** failure tour, full rehearsals ×3 on real glasses, backup video recorded from a rehearsal, eval chart, deck final, consent sign printed. Feature freeze at hour 30; hours 33–34 are buffer. | All. D owns deck and video |

## 7. Non-code deliverables and pilot path (D2, D4, D5)
- **Deck (10 slides):** the problem (the unbooked gap, the interpreter shortage figures with a caveat), the audience, the scenario, why first-person view, a live-demo slide, architecture and data flow (what leaves the device), **an honest eval chart** (held-out signer), the "What we are not" design response to WFD/efsli, the pilot, and the ask.
- **75 s demo video** of the classroom-door scenario: glasses POV capture plus a third-person shot plus the Duet card. It doubles as a backup if the live demo fails.
- **Live-demo kit:** a printed consent and privacy sign at the table, a QR code for the Duet card, a scripted 6-phrase sequence, and the webcam fallback rehearsed.
- **Pilot path:** (1) a co-design session with Kuurojen Liitto (deaf-led, data owned by the signers), (2) a 4-week pilot at one site: a school with deaf pupils, or a university accessibility desk or the Oodi library desk. The vocabulary of ~50 FinSL signs is taught **by deaf staff through Teach mode**. (3) Success = the share of confirmed phrases, a signer-rated "accurate and respectful" score of ≥4/5, and the median time to understand a request compared with pen and paper. The deck states that no partner has been contacted yet.

## 8. Risks and cut list
| Risk | Mitigation |
|---|---|
| Camera and display cannot share one DAT session | Web App HUD fallback, decided in M0 |
| Android DAT frames fail or a device is unavailable | iOS only if a paid team exists; otherwise the phone or webcam source plus the glasses HUD, labelled honestly |
| Glasses camera too blurry or low-res for handshapes | shoulder-normalised features; a signing distance of 1–1.5 m; the vocabulary is chosen for big movements; fingerspelling is only a stretch |
| Low accuracy on the held-out signer | the confidence tiers abstain instead of guessing; ✓/✗; publish the real number; Teach mode adapts to the signer |
| LLM hallucinates content | the gloss-only validator; the raw glosses are always visible; the template fallback |
| Latency over 2 s feels broken | LLM only at the end of an utterance, a Haiku-class model, local ML, a "listening…" HUD state |
| Thermal limits or session drops in the live demo | stream only while consent is ON; short bursts; a spare device and the backup video |
| Shared devices on old firmware | update in M0; reserve a device for judging (BRIEF Q3) |

**Cut list (drop in this order):** Gemini verifier → fingerspelling → Neural Band input (use phone buttons) → NMM negation (keep the question flag) → GRU (keep kNN) → LLM assembler (template only) → DAT Display (use the Web App HUD). **Never cut:** consent/Start-Stop, the confidence tiers, wearer speech → card captions, the D3 states, and the held-out eval. Teach-a-sign is cut only if M2 is late at hour 24.

## 9. Self-score (0–10)
| Criterion | Score | Why |
|---|---|---|
| J1 Creativity and use case | 9 | It reverses the usual "captions for deaf wearer" product into a true two-way loop on Ray-Ban Display; teaching a sign live is a memorable moment on stage. |
| J2 Technical execution | 7 | It uses native DAT camera, display, inputs and audio, local ML, a validated LLM and held-out eval, but it carries the most integration risk; the fallbacks keep a working demo. |
| J3 Real-world value and feasibility | 8 | It targets the real unbooked gap with a concrete FinSL pilot through Teach mode; its limits are a bounded vocabulary and no co-design yet. |
| J4 UX: input, accessibility, trust | 9 | The signer has their own screen, consent, veto and captions; it shows confidence, abstains when unsure, and gives a live accuracy readout and a plain privacy note. |
