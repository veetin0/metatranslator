# Plan

Time budget: ~37 h (2026-11-13 21:00 → 2026-11-15 10:00 EET) · Deadline: 2026-11-15T10:00+02:00 · Team: 4 (lead + Aadit, einoperamaa, Topias) · Profile: lean (plan: pro) · Stack (revision 2, 2026-11-13, modelled on Meta's DAT iOS sample `samples/BirdSpotter`):
- **"Signer" native phone app on DAT 1.0.1.** One `DeviceSession` does three things:
  - streams the glasses camera to the core;
  - shows captions on Ray-Ban Display with DAT Display cards (`FlexBox`/`Text`);
  - speaks them with phone TTS, which reaches the glasses because they are the phone's Bluetooth audio output.
- **Platform:** iOS Swift if a paid Apple team is confirmed (recommended: the lead has Xcode and the reference sample is iOS), else Android Kotlin. M0 decides and only one is built.
- **Without glasses:** Mock Device Kit with `metaRayBanDisplay` preview, or a Simulator build that streams to the Chrome Display Simulator.
- **The Signer Web App is the caption fallback** and the quick browser preview of the lens.
- **Python Signer Core on a laptop:** MediaPipe + kNN/GRU, pretrained on the Kaggle `asl-signs` landmarks (250 signs). One pipeline for glasses, webcam and eval.
- **Signer Card:** a static web page.
- **English only (ASL → English).**

Decision and cut list: DECISION.md. Sources: research/webapps-and-datasets.md, research/platform.md (BirdSpotter notes in section 4 of webapps-and-datasets.md).

All times EET (Helsinki). Feature freeze **Sun 02:30**. Last 20 %: Sun 02:30–08:30 pitch, verify, perfect loop. Sun 08:30–10:00 submission reserve (90 min, `loop.reserve_minutes`).

## Repo layout (owned paths; tasks never share one)
| Path | What |
|---|---|
| `glasses-app/` | Native DAT app (iOS `glasses-app/ios/` **or** Android `glasses-app/android/`, decided in M0), BirdSpotter structure: session/camera/display/mock repositories + `AppContainer` + view-model; camera → core, captions → DAT Display, TTS, reply STT, lifecycle/device-state UI |
| `core/signer_core/` | Python package: `relay/` (FastAPI + WS), `vision/` (MediaPipe, features, segmenter), `model/` (kNN, GRU, teach), `language/` (templates, LLM + validator), `sources/` (webcam, glasses frames) |
| `core/tests/` | pytest |
| `core/tools/record.py` | landmark recording tool (stores landmarks `.npz`, never video) |
| `eval/` | `eval/run.py` LOSO harness, `eval/results/*.json` |
| `data/landmarks/` | recorded landmark clips (`<signer>/<gloss>/<n>.npz`), team signers consented |
| `card/` | Signer Card web page (served by core) |
| `hud-web/` | Signer glasses Web App (600x600, `mrbd-web-app-capable`, WSS client, speechSynthesis, < 300 KB). Two jobs: the browser lens preview in the Display Simulator for glasses-free development, and Fallback A. |
| `core/tools/tunnel.sh` | cloudflared HTTPS/WSS tunnel, only for the Web App on the device |
| `data/kaggle/` | Kaggle `asl-signs` landmark parquet, gitignored and downloaded by script |
| `deck/`, `video/`, `demo/` | deck, demo video pipeline, live-demo kit |
| `.hackforge/evidence/` | screenshots, latency logs, hardware tick sheets |

## Milestones (vertical slices)
| M | Goal | Covers | Acceptance checks (runnable / evidence) | Time-box | Status |
|---|------|--------|------------------------------|----------|--------|
| M0 | **Go/no-go spike on hardware** (`needs-spike`). Prerequisites: Meta AI app ≥ V292, firmware ≥ V128, Developer Mode. **Platform pick:** paid Apple team → build BirdSpotter/CameraAccess on iOS, else the Android samples; registered in the Meta AI app. Then check: (a) glasses camera frames reach the phone at medium 504x896 ≥ 7 fps (BirdSpotter only proves `.low`/7 fps); (b) **"Hello" DAT Display card shown while the camera streams in the same session**; (c) phone TTS audible in the glasses speaker while streaming; (d) frames reach the laptop over USB tethering while the glasses stream, and captions come back; (e) fallback check: the Signer Web App hello installs via QR and opens on the device; (f) latency (sign end → lens) + a 10 min thermal note. In parallel, without glasses: install the Display Simulator extension + Meta's webapp plugin/docs MCP; webcam MediaPipe ≥ 15 fps; download Kaggle `asl-signs`, confirm its licence and freeze the 24-sign vocabulary against `sign_to_prediction_index_map.json`; record tool works. | R1, R2, D3 | `.hackforge/evidence/M0-spike.md` with pass/fail per (a)–(f) + photos; simulator screenshot `M0-sim-hello.png`; `python -m signer_core.sources.webcam --bench 10` prints fps ≥ 15; `python core/tools/record.py --dry-run` exits 0; `data/VOCAB.md` lists 24 signs with their source (Kaggle / own) | Fri 21:00–23:00 | ⬜ |
| M1 | **Thinnest end-to-end, no glasses:** webcam → core → 24-sign classifier (kNN on own clips + Kaggle-pretrained encoder/prototypes) → template sentence → caption in the `hud-web/` Web App running in the **Display Simulator** + `speechSynthesis`; confidence tiers; minimal Signer Card with consent Start/Stop gating the stream. Record 3–4 team signers × 20 clips × 25 classes. Eval v0: LOSO on own clips + Kaggle held-out signers. | D1, J2, J4, R3 | `pytest core/tests -q` green; `python eval/run.py --loso --out eval/results/m1.json` prints top-1/selective acc/abstain (own + Kaggle); `curl localhost:8000/health` → ok; simulator screenshot of caption + card Start→caption→Stop in evidence | Fri 23:00–Sat 07:00 | ⬜ |
| M2 | **On the glasses:** DAT stream → USB → core → caption card on Ray-Ban Display via DAT Display (Web App if M0 picked Fallback A) + phone TTS in the glasses speaker; state machine for registration/permission/session PAUSED/STOPPED/device state (BirdSpotter's session repository as reference); consent reset on STOPPED; "core down" state; glasses-camera clips recorded for domain-shift eval; GRU tried. | R1, R2, D3, J2 | app unit tests green (`xcodebuild test` or `./gradlew :app:testDebugUnitTest`, incl. a Mock Device Kit display-preview test); `python eval/run.py --loso --source glasses` writes `eval/results/m2.json`; evidence `M2-display-caption.jpg`, `M2-latency.log` (sign end → caption), hardware tick by owner | Sat 07:00–14:00 | ⬜ |
| M3 | **Two-way + trust + grafts:** reply STT (phone mic) → card captions, typed-reply fallback; ✓/✗ + live readout ("17/19 confirmed") on card + HUD footer; "Not right" veto; Teach-a-sign (5 reps → kNN prototypes, delete); LLM fluent mode (Claude Haiku 4.5, gloss text only) with gloss-only validator + offline template fallback; question flag (brows); 3 triggerable D3 states shown (permission denied, glasses off, core down) + "Link slow" chip; idle auto-stop 2 min. Each graft behind a flag. | J1, J3, J4, D3, R3 | `pytest core/tests -q` incl. `test_validator.py`, `test_teach.py`, `test_consent.py`; `python eval/run.py --loso --out eval/results/m3.json`; evidence: card screenshots of each state, failure-tour clip | Sat 14:00–21:00 (Teach cut at 18:00 if M2 late) | ⬜ |
| M4 | **Demo-proof:** final held-out eval (+ unseen volunteer signer if consented), eval chart, 3 timed rehearsals on real glasses, backup video recorded from a rehearsal, deck v1, live-demo kit printed. | D1, D2, D4, D5, all J | `python eval/run.py --loso --report eval/results/final.json`; `deck/` exports PDF; `video/out/demo.mp4` exists, 60–90 s; `demo/rehearsals.md` with 3 timed runs | Sat 21:00–Sun 02:30 (freeze) | ⬜ |

## Tasks per milestone
| M | Role | Task (id) | Owned paths | Depends on contract | Agent / model | Status |
|---|---|---|---|---|---|---|
| M0 | full-stack (hardware) | M0.1 DAT spike from BirdSpotter/CameraAccess (iOS) or the Android samples: registration, camera frames at medium, DAT Display hello during streaming, TTS to glasses, USB-tether frames to laptop | `glasses-app/` | — | human + sonnet | ⬜ |
| M0 | frontend | M0.2 Signer Web App hello (fallback + lens preview): `mrbd-web-app-capable` page, WSS echo, speechSynthesis, HTTPS deploy + `fb-viewapp://` QR, simulator + device; cloudflared tunnel script | `hud-web/`, `core/tools/tunnel.sh` | — | sonnet | ⬜ |
| M0 | data-ml | M0.3 Core scaffold: webcam source + MediaPipe Holistic bench ≥ 15 fps, features in the same 543-landmark layout as Kaggle | `core/signer_core/vision/`, `core/signer_core/sources/`, `core/pyproject.toml` | frame contract | sonnet | ⬜ |
| M0 | data-ml | M0.4 Kaggle `asl-signs` download script + licence check, vocabulary (24 + REST, from the Kaggle list where possible), landmark record tool | `core/tools/record.py`, `core/tools/get_kaggle.py`, `data/VOCAB.md` | landmark file format | sonnet | ⬜ |
| M1 | data-ml | M1.1 Segmenter + Kaggle-pretrained encoder (or prototypes) + kNN on own clips + confidence | `core/signer_core/model/`, `core/tests/test_model.py` | landmark format | sonnet | ⬜ |
| M1 | backend | M1.2 Relay: FastAPI + WS, consent state machine, template sentences, frame ingest endpoint | `core/signer_core/relay/`, `core/signer_core/language/`, `core/tests/test_relay.py` | relay API | sonnet | ⬜ |
| M1 | frontend | M1.3 Signer Card v0 (consent, ON light, history) + Signer Web App caption view (additive-display design, D-pad focus) + speechSynthesis, tested in Display Simulator | `card/`, `hud-web/` | relay WS events | sonnet | ⬜ |
| M1 | data-ml | M1.4 Record clips (all 4 people) + eval harness LOSO | `data/landmarks/`, `eval/` | landmark format | human + sonnet | ⬜ |
| M2 | full-stack | M2.1 Glasses app: stream → USB → core, captions back → DAT Display caption card (throttled; tiers: ✓ white, "?" amber, "didn't catch that") + phone TTS, state machine + lifecycle UI, Mock Device Kit display-preview test | `glasses-app/` | relay API + caption card spec | human + sonnet | ⬜ |
| M2 | data-ml | M2.2 GRU + glasses-source eval + crop/normalisation tuning | `core/signer_core/model/`, `eval/` | — | sonnet | ⬜ |
| M2 | backend | M2.3 Glasses frame source + core state events (paused/stopped/slow link) + consent reset | `core/signer_core/sources/`, `core/signer_core/relay/` | relay API | sonnet | ⬜ |
| M2 | frontend | M2.4 Lens state designs shared by DAT cards and the Web App mirror (connecting, ON, paused, core down, link slow), card state screens | `hud-web/`, `card/` | HUD layout spec | sonnet | ⬜ |
| M3 | full-stack | M3.1 Glasses app: reply STT (phone mic; MWDATSpeech only if stable, as it's experimental) + typed fallback + D3 triggerable states + idle auto-stop | `glasses-app/` | relay API | sonnet | ⬜ |
| M3 | backend | M3.2 LLM fluent mode + gloss-only validator + offline fallback + question flag | `core/signer_core/language/`, `core/signer_core/vision/face.py` | — | sonnet | ⬜ |
| M3 | data-ml | M3.3 Teach-a-sign (5 reps → prototypes, delete) + ✓/✗ readout counter | `core/signer_core/model/teach.py`, `core/signer_core/relay/feedback.py` | relay API | sonnet | ⬜ |
| M3 | frontend | M3.4 Card: ✓/✗, Not right, Teach UI, reply captions, privacy note, QR | `card/` | relay WS events | sonnet | ⬜ |
| M4 | pitch | M4.1 Deck (problem/audience, why first-person, demo, data flow, honest eval, "What we are not", consent, pilot) | `deck/` | — | sonnet | ⬜ |
| M4 | craft:video | M4.2 60–90 s demo video from a real rehearsal | `video/` | asset spec | sonnet | ⬜ |
| M4 | data-ml | M4.3 Final eval + chart + volunteer signer run | `eval/` | — | sonnet | ⬜ |
| M4 | pitch | M4.4 Live-demo kit: consent sign, volunteer form, scripted phrases, rehearsal log | `demo/` | — | human + sonnet | ⬜ |

## Non-code deliverables
| Asset | Raises | Spec (in CONTRACTS.md at build) | Tool | Status |
|---|---|---|---|---|
| Deck 8–10 slides (PDF) | D2, D4, D5, J3 | honest numbers only, English/ASL scope, dataset credits (Kaggle/PopSign CC BY), "how it ships on the glasses" slide (DAT app: camera + display + speaker in one session; Web App fallback), no partner/endorsement claims | HTML/Marp → PDF | ⬜ |
| Demo video 60–90 s, 16:9 | J1, J4, backup for J2 | real glasses POV + third-person + card; follows the user's global pitch-video rules (no "Eric" voice — confirm voice with user first; music that builds with one or two drops; one continuous VO take split by word timings; playful but honest) | Remotion/HyperFrames + ffmpeg | ⬜ |
| Live-demo kit | J4, R3 | printed "camera in use, nothing recorded" sign, volunteer consent form, 6-phrase script, QR to card | print | ⬜ |
| Eval chart | J2, J4 | LOSO + glasses-camera + latency, measured values only | matplotlib | ⬜ |
| Pilot one-pager (draft) | J3, D5 | deaf-led co-design with an English-speaking (ASL) school/service desk → 1 site, 4 weeks, new signs via Teach; "not contacted" | markdown | ⬜ |

## Sleep and ownership
Two shifts so the critical path is always covered: Android owner + ML owner sleep ~Sat 02:00–06:00; card/HUD owner + data/deck owner ~Sat 04:00–08:00. Suggested owners (lead confirms): glasses app (iOS or Android) = the lead on the Mac with Xcode if iOS, else whoever has the Android phone; ML core = Topias; relay + card = Aadit; HUD + data/eval + deck = einoperamaa; lead integrates.

## Open questions for the lead (answer at plan acceptance)
1. **Platform:** Is there a paid Apple developer team plus an iPhone on iOS 17.2+? If yes, we build on iOS from BirdSpotter. If not, does someone have an Android 10+ phone with Android Studio (+30–60 min in M0)?
2. Can a Ray-Ban Display be reserved for final judging (BRIEF Q3)? Ask Amanda Le at the Meta booth tonight.
3. Pitch length / is a demo video required (BRIEF Q1)?
4. Is "English sign language" ASL (assumed, because it has the open datasets) or BSL? BSL data is research-only video, and switching to it costs about 4 h of landmark extraction.
5. Is it OK to install Meta's `meta-wearables-webapp` Claude Code plugin and the docs MCP (`mcp.developer.meta.com/wearables`)? Does someone have a Kaggle account to download `asl-signs`?

Polish & submission reserve: last 20 % (from Sun 02:30), with the final 90 min (Sun 08:30–10:00) kept for submission only.
