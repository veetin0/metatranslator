# Plan

Time budget: ~37 h (2026-11-13 21:00 → 2026-11-15 10:00 EET) · Deadline: 2026-11-15T10:00+02:00 · Team: 4 (lead + Aadit, einoperamaa, Topias) · Profile: lean (plan: pro) · Stack: Android Kotlin + Meta DAT 1.0.1 (only official camera path; DAT Display draws on Ray-Ban Display), Python Signer Core on a laptop (MediaPipe + kNN/GRU, one pipeline for glasses, webcam and eval), static web Signer Card + glasses Web App fallback. Decision and cut list: DECISION.md.

All times EET (Helsinki). Feature freeze **Sun 02:30**. Last 20 %: Sun 02:30–08:30 pitch, verify, perfect loop. Sun 08:30–10:00 submission reserve (90 min, `loop.reserve_minutes`).

## Repo layout (owned paths; tasks never share one)
| Path | What |
|---|---|
| `android/` | Kotlin DAT app (camera bridge, DAT Display HUD, TTS, STT, state machine) |
| `core/signer_core/` | Python package: `relay/` (FastAPI + WS), `vision/` (MediaPipe, features, segmenter), `model/` (kNN, GRU, teach), `language/` (templates, LLM + validator), `sources/` (webcam, glasses frames) |
| `core/tests/` | pytest |
| `core/tools/record.py` | landmark recording tool (stores landmarks `.npz`, never video) |
| `eval/` | `eval/run.py` LOSO harness, `eval/results/*.json` |
| `data/landmarks/` | recorded landmark clips (`<signer>/<gloss>/<n>.npz`), team signers consented |
| `card/` | Signer Card web page (served by core) |
| `hud-web/` | 600x600 glasses Web App HUD (fallback + browser-sim of the lens) |
| `deck/`, `video/`, `demo/` | deck, demo video pipeline, live-demo kit |
| `.hackforge/evidence/` | screenshots, latency logs, hardware tick sheets |

## Milestones (vertical slices)
| M | Goal | Covers | Acceptance checks (runnable / evidence) | Time-box | Status |
|---|------|--------|------------------------------|----------|--------|
| M0 | **Go/no-go spike on hardware** (`needs-spike`): Meta AI app ≥ V292, firmware ≥ V128, Dev Mode, Android DAT sample registered; (a) glasses frames on phone, (b) "Hello" on DAT Display **while** streaming, (c) TTS audible in glasses, (d) frames reach laptop over USB tethering while glasses stream, (e) Web App HUD hello in simulator + device, (f) latency + 10 min thermal note. In parallel: webcam MediaPipe ≥ 15 fps, vocab frozen, record tool works. | R1, R2, D3 | `.hackforge/evidence/M0-spike.md` with pass/fail per (a)–(f) + photos; `python -m signer_core.sources.webcam --bench 10` prints fps ≥ 15; `python core/tools/record.py --dry-run` exits 0 | Fri 21:00–23:00 | ⬜ |
| M1 | **Thinnest end-to-end (webcam):** webcam → core → 24-sign kNN → template sentence → caption in `hud-web/` lens view + TTS; confidence tiers; minimal Signer Card with consent Start/Stop gating the stream. Record 3–4 team signers × 20 clips × 25 classes. Eval v0 (LOSO). | D1, J2, J4, R3 | `pytest core/tests -q` green; `python eval/run.py --loso --out eval/results/m1.json` prints top-1/selective acc/abstain; `curl localhost:8000/health` → ok; card Start→caption→Stop browser screenshot in evidence | Fri 23:00–Sat 07:00 | ⬜ |
| M2 | **On the glasses:** DAT stream → USB → core → caption on Ray-Ban Display (or Web App HUD per M0) + TTS in glasses speaker; state machine for registration/permission/session PAUSED/STOPPED/device state; consent reset on STOPPED; glasses-camera clips recorded for domain-shift eval; GRU tried. | R1, R2, D3, J2 | `./gradlew :app:testDebugUnitTest` green; `python eval/run.py --loso --source glasses` writes `eval/results/m2.json`; evidence `M2-display-caption.jpg`, `M2-latency.log` (sign end → caption), hardware tick by owner | Sat 07:00–14:00 | ⬜ |
| M3 | **Two-way + trust + grafts:** reply STT (phone mic) → card captions, typed-reply fallback; ✓/✗ + live readout ("17/19 confirmed") on card + HUD footer; "Not right" veto; Teach-a-sign (5 reps → kNN prototypes, delete); LLM fluent mode (Claude Haiku 4.5, gloss text only) with gloss-only validator + offline template fallback; question flag (brows); 3 triggerable D3 states shown (permission denied, glasses off, core down) + "Link slow" chip; idle auto-stop 2 min. Each graft behind a flag. | J1, J3, J4, D3, R3 | `pytest core/tests -q` incl. `test_validator.py`, `test_teach.py`, `test_consent.py`; `python eval/run.py --loso --out eval/results/m3.json`; evidence: card screenshots of each state, failure-tour clip | Sat 14:00–21:00 (Teach cut at 18:00 if M2 late) | ⬜ |
| M4 | **Demo-proof:** final held-out eval (+ unseen volunteer signer if consented), eval chart, 3 timed rehearsals on real glasses, backup video recorded from a rehearsal, deck v1, live-demo kit printed. | D1, D2, D4, D5, all J | `python eval/run.py --loso --report eval/results/final.json`; `deck/` exports PDF; `video/out/demo.mp4` exists, 60–90 s; `demo/rehearsals.md` with 3 timed runs | Sat 21:00–Sun 02:30 (freeze) | ⬜ |

## Tasks per milestone
| M | Role | Task (id) | Owned paths | Depends on contract | Agent / model | Status |
|---|---|---|---|---|---|---|
| M0 | full-stack (hardware) | M0.1 Android DAT spike: sample app, registration, camera frames, Display hello while streaming, TTS, USB-tether frames to laptop | `android/` | — | human + sonnet | ⬜ |
| M0 | frontend | M0.2 Web App HUD hello (simulator + device), Apple paid-team check | `hud-web/` | — | sonnet | ⬜ |
| M0 | data-ml | M0.3 Core scaffold: webcam source + MediaPipe Hands/Pose bench ≥ 15 fps, features | `core/signer_core/vision/`, `core/signer_core/sources/`, `core/pyproject.toml` | frame contract | sonnet | ⬜ |
| M0 | data-ml | M0.4 Vocabulary (24 + REST, dictionary links) + landmark record tool | `core/tools/record.py`, `data/VOCAB.md` | landmark file format | sonnet | ⬜ |
| M1 | data-ml | M1.1 Segmenter + kNN/DTW classifier + confidence | `core/signer_core/model/`, `core/tests/test_model.py` | landmark format | sonnet | ⬜ |
| M1 | backend | M1.2 Relay: FastAPI + WS, consent state machine, template sentences, frame ingest endpoint | `core/signer_core/relay/`, `core/signer_core/language/`, `core/tests/test_relay.py` | relay API | sonnet | ⬜ |
| M1 | frontend | M1.3 Signer Card v0 (consent, ON light, history) + lens view in `hud-web/` + browser TTS | `card/`, `hud-web/` | relay WS events | sonnet | ⬜ |
| M1 | data-ml | M1.4 Record clips (all 4 people) + eval harness LOSO | `data/landmarks/`, `eval/` | landmark format | human + sonnet | ⬜ |
| M2 | full-stack | M2.1 Android: stream → USB → core, DAT Display caption renderer, TTS, state machine + lifecycle UI | `android/` | relay API | human + sonnet | ⬜ |
| M2 | data-ml | M2.2 GRU + glasses-source eval + crop/normalisation tuning | `core/signer_core/model/`, `eval/` | — | sonnet | ⬜ |
| M2 | backend | M2.3 Glasses frame source + core state events (paused/stopped/slow link) + consent reset | `core/signer_core/sources/`, `core/signer_core/relay/` | relay API | sonnet | ⬜ |
| M2 | frontend | M2.4 HUD states (DAT layouts spec + Web App mirror), card state screens | `hud-web/`, `card/` | HUD layout spec | sonnet | ⬜ |
| M3 | full-stack | M3.1 Android reply STT + typed fallback + D3 triggerable states + idle auto-stop | `android/` | relay API | sonnet | ⬜ |
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
| Deck 8–10 slides (PDF) | D2, D4, D5, J3 | honest numbers only, cited ranges (3,000–5,000 FinSL signers), no partner/endorsement claims | HTML/Marp → PDF | ⬜ |
| Demo video 60–90 s, 16:9 | J1, J4, backup for J2 | real glasses POV + third-person + card; follows the user's global pitch-video rules (no "Eric" voice — confirm voice with user first; music that builds with one or two drops; one continuous VO take split by word timings; playful but honest) | Remotion/HyperFrames + ffmpeg | ⬜ |
| Live-demo kit | J4, R3 | printed "camera in use, nothing recorded" sign, volunteer consent form, 6-phrase script, QR to card | print | ⬜ |
| Eval chart | J2, J4 | LOSO + glasses-camera + latency, measured values only | matplotlib | ⬜ |
| Pilot one-pager (draft) | J3, D5 | Kuurojen Liitto co-design → 1 site, 4 weeks, FinSL via Teach; "not contacted" | markdown | ⬜ |

## Sleep and ownership
Two shifts so the critical path is always covered: Android owner + ML owner sleep ~Sat 02:00–06:00; card/HUD owner + data/deck owner ~Sat 04:00–08:00. Suggested owners (lead confirms): Android/DAT = whoever has the DAT-compatible Android phone; ML core = Topias; relay + card = Aadit; HUD + data/eval + deck = einoperamaa; lead integrates.

## Open questions for the lead (answer at plan acceptance)
1. Does someone have a DAT-compatible Android 10+ phone, and Android Studio installed (else +30–60 min in M0)? Is there a paid Apple developer team?
2. Can a Ray-Ban Display be reserved for final judging (BRIEF Q3)? Ask Amanda Le at the Meta booth tonight.
3. Pitch length / is a demo video required (BRIEF Q1)?

Polish & submission reserve: last 20 % (from Sun 02:30), with the final 90 min (Sun 08:30–10:00) kept for submission only.
