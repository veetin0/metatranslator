# Contracts (frozen 2026-11-13; change only by a recorded contract change in STATE.md)

Read with PLAN.md (owned paths), DECISION.md (data practice R3, tiers), DESIGN.md (look). Meta references for every builder: Display Simulator https://chromewebstore.google.com/detail/jpjlmmodokemlepklkdbimceggpbjcll · DAT https://wearables.developer.meta.com/docs/develop/dat/getting-started-toolkit · Web Apps https://wearables.developer.meta.com/docs/develop/webapps · repos github.com/meta/meta-wearables-webapp, meta-wearables-dat-ios (sample `samples/BirdSpotter`), meta-wearables-dat-android · docs MCP `https://mcp.developer.meta.com/wearables` (`search_webapps_docs`, `search_dat_docs`).

## 0. Shared code (not owned by any task; change = contract change)
- `core/signer_core/contracts.py` — the Python types below (events, landmark layout, tiers). Every core module imports from here.
- `contracts/events.example.jsonl` — one example of every WS event; front-ends use it as mock data.
- `.env.example`, `README.md` skeleton, `.hackforge/gate.sh`.

## 1. Data flow
Glasses camera → (DAT `DeviceSession`, `.raw`/`.hvc1`, medium 504×896) → iPhone app → JPEG over **WS `/ws/frames`** (USB tethering) → core: MediaPipe Holistic → landmarks (RAM only, frame dropped) → segmenter → classifier → gloss sequence → English sentence → **WS `/ws/events`** → glasses app (DAT Display card + `AVSpeechSynthesizer`), Signer Card, Web App mirror.
Dev sources use the same path: `signer_core.sources.webcam` pushes frames in-process; Mock Device Kit plays h265 clips as the glasses camera.

## 2. Relay API (core, FastAPI, default `http://<laptop>:8000`)
| Method + path | Request | Response |
|---|---|---|
| `GET /health` | — | `{"status":"ok","version":"0.1.0","model":"knn"|"gru","vocab":24,"session":"off"|"on"|"paused"}` |
| `GET /vocab` | — | `{"signs":[{"gloss":"HELLO","english":"hello","source":"popsign"|"own"|"taught"}]}` |
| `GET /session` | — | `Session` |
| `POST /session/start` | `{"by":"card"|"app"}` | `Session` (state `on`); 409 `{"error":"no_consent"}` never happens from the card because Start *is* consent |
| `POST /session/stop` | `{"by":"card"|"app"|"idle"|"device"}` | `Session` (state `off`) |
| `POST /feedback` | `{"caption_id":"c42","verdict":"right"|"wrong"|"veto"}` | `{"confirmed":17,"total":19}` |
| `POST /reply` | `{"text":"Sure, page 12","source":"stt"|"typed"}` | `{"ok":true}` (broadcast as `reply`) |
| `POST /teach` (M3) | `{"gloss":"PROJECTOR","english":"projector"}` | `{"teach_id":"t1","reps_needed":5}`; next 5 segments are captured as prototypes |
| `GET /teach` (M3) | — | `{"taught":[{"gloss","english","reps"}]}` |
| `DELETE /teach/{gloss}` (M3) | — | `{"deleted":true}` |
| `GET /` | — | Signer Card (`card/index.html`, static) |
| `WS /ws/frames` | producer → core, binary | see §3; core replies text `{"type":"ack","seq":n}` every 30 frames |
| `WS /ws/events` | core → consumers (text JSON), consumers → core (`feedback`, `reply`) | see §4 |

`Session` = `{"session_id":"s1"|null,"state":"off"|"on"|"paused","since":<unix ms>,"by":"card"}`.
Frames are rejected (WS close 4403 `consent_required`) unless the session is `on`. Session goes `off` on Stop, on idle `SIGNER_IDLE_STOP_S` (default 120 s without a segment), and on device `STOPPED` (app calls `/session/stop` with `by:"device"`): **consent resets, a new Start is needed**.

## 3. Frame message (`/ws/frames`, binary)
`[4-byte big-endian uint32 header length][UTF-8 JSON header][JPEG bytes]`
Header: `{"seq":123,"ts_ms":1731520000123,"w":504,"h":896,"source":"glasses"|"webcam"|"mock","rot":0}`. JPEG quality 70. Target ≥ 10 fps, core drops frames older than 300 ms. Frames are never written to disk.

## 4. Events (`/ws/events`, JSON text, one object per message)
Core → clients:
- `{"type":"state","state":"off"|"connecting"|"on"|"paused"|"glasses_off"|"permission_denied"|"core_down","link":"ok"|"slow","ts":<ms>}` — `link:"slow"` when frame age p50 > 300 ms over 3 s. `core_down` is produced by *clients* when the socket drops (> 2 s), never sent by the core.
- `{"type":"partial","gloss":"HELLO","confidence":0.62,"ts":<ms>}` — optional live hint, card only.
- `{"type":"caption","id":"c42","text":"Hello, can I ask a question?","gloss":["HELLO","QUESTION"],"tier":"confirmed"|"unsure"|"none","confidence":0.86,"alternatives":[{"text":"…","gloss":["…"],"confidence":0.41}],"question":false,"mode":"template"|"llm","speak":true,"ts":<ms>}` — `speak` is true only for `confirmed`. `none` has `text:"Didn't catch that"`.
- `{"type":"retract","id":"c42"}` — after a veto; lens removes it.
- `{"type":"reply","text":"Sure, page 12","source":"stt"|"typed","ts":<ms>}`
- `{"type":"stats","confirmed":17,"total":19}`
Clients → core: `{"type":"feedback","caption_id":"c42","verdict":"right"|"wrong"|"veto"}`, `{"type":"reply","text":"…","source":"stt"|"typed"}`, `{"type":"hello","client":"app"|"card"|"hud"}`, and from the iOS app only `{"type":"state","state":"glasses_off"|"permission_denied"|"on","link":"ok","ts":<ms>,"from":"app"}`.
**App state relay (contract change M3, lead 2026-11-14):** the core passes an app `state` message on to every other `/ws/events` client unchanged (with `"from":"app"`), so the card shows glasses off / permission denied. It never changes the consent session; `"on"` clears the app's fault. Core-originated `state` events have no `from`.

**Tiers** (DECISION.md, env-tunable): confidence ≥ `SIGNER_CONF_HIGH` (0.80) → `confirmed` (show + speak); ≥ `SIGNER_CONF_LOW` (0.50) → `unsure` (amber "?" + top-2, not spoken); else `none`.

## 5. Landmark clip file (`.npz`, `np.savez_compressed`)
Path: `data/landmarks/<signer>/<GLOSS>/<n>.npz` (own), `data/popsign/landmarks/<GLOSS>/<clip_id>.npz` (PopSign), `data/glasses/<signer>/<GLOSS>/<n>.npz` (glasses-camera, M2).
Keys: `xyz` float16 `(T, 75, 3)`; `t_ms` int64 `(T,)`; `fps` float32 scalar; `gloss` str; `signer` str (pseudonym, e.g. `s1`; PopSign: their signer id); `source` str `own|popsign|glasses|webcam`.
Point layout (`signer_core.contracts.LAYOUT`): 0–32 MediaPipe Pose (33), 33–53 left hand (21), 54–74 right hand (21). x, y normalised image coords [0, 1], z MediaPipe relative depth; missing hand/pose = NaN. **Change from PLAN M0.3's "543 layout":** face mesh is not stored (size: 4,400 clips × 543 points would be ~1 GB in git; 75 points float16 is ~120 MB) — the question flag reads face blendshapes live only.
REST class = `"REST"`. Features (`vision/features.py`): shoulder-centred, shoulder-width-scaled coords + hand joint angles; resampled to 32 steps for kNN.
`data/VOCAB.md`: table `| GLOSS | english | source (popsign/own) | popsign_name |`, 24 signs + REST. `data/popsign/raw/` (videos) is gitignored and deleted after extraction.

## 6. Eval output (`eval/results/<name>.json`)
`{"name":"m1","protocol":"loso","sources":["own","popsign"],"signers":["s1","s2","s3","s4"],"top1":0.0,"top3":0.0,"selective_acc":0.0,"coverage":0.0,"abstain_rate":0.0,"per_class":{"HELLO":{"n":20,"top1":0.0}},"latency_ms_p50":null,"n_clips":0,"created":"<iso>"}`.
`selective_acc` = accuracy on `confirmed`-tier predictions; `coverage` = share predicted `confirmed`. CLI: `python eval/run.py --loso [--source own|popsign|glasses] --out eval/results/<name>.json` (`--report` also writes `eval/results/<name>.png`). Numbers in deck/pitch come only from these files.

## 7. Lens specs (DESIGN.md has the look)
- **DAT Display card** (`glasses-app/`): `FlexBox` column, black, caption `Text` ≤ 2 lines × ~24 chars, state line top, readout footer. Send at most every 500 ms and only on change; only while session state is `.streaming`.
- **Web App** (`hud-web/`): static, 600×600, `<meta name="mrbd-web-app-capable" content="yes">` per Meta Web Apps docs, black background, first load < 300 KB (no web fonts), connects to `?core=wss://…/ws/events` (default `ws://127.0.0.1:8000/ws/events` for the simulator), `speechSynthesis` for `speak:true`, D-pad focus (works with Chrome `--enable-spatial-navigation`). `npm run build` → `hud-web/dist/`; `npm run preview -- --host 127.0.0.1 --port 4173`. Hosted on GitHub Pages; core WSS via `core/tools/tunnel.sh` (cloudflared quick tunnel) only for the device.

## 8. iOS app (`glasses-app/ios/`)
Xcode ≥ 26.4, iOS 17.2+, Swift, DAT 1.0.1 via SwiftPM (`MWDATCore`, `MWDATCamera`, `MWDATDisplay`, `MWDATMockDevice`). Project `glasses-app/ios/Signer.xcodeproj`, scheme `Signer`, test target `SignerTests`. BirdSpotter structure: `SessionRepository`, `CameraRepository`, `DisplayRepository`, `MockDeviceRepository`, `CoreClient` (WS frames + events), `SpeechService` (AVSpeechSynthesizer), `AppContainer`, `SignerViewModel`. Settings: core URL (default `ws://172.20.10.2:8000`, the Mac on iPhone USB tethering), Info.plist `MetaAppID` (0 in Developer Mode, or the Developer Center ID), analytics opt-out. Test: `xcodebuild test -project glasses-app/ios/Signer.xcodeproj -scheme Signer -destination 'platform=iOS Simulator,name=iPhone 17'`.

## 9. Environment variables (`.env.example`)
`SIGNER_HOST=0.0.0.0`, `SIGNER_PORT=8000`, `SIGNER_MODEL=knn` (`gru`), `SIGNER_CONF_HIGH=0.80`, `SIGNER_CONF_LOW=0.50`, `SIGNER_IDLE_STOP_S=120`, `SIGNER_DATA_DIR=data`, `SIGNER_LLM=off` (`haiku`), `SIGNER_LLM_MODEL=claude-haiku-4-5-20251001`, `ANTHROPIC_API_KEY=` (only gloss text is ever sent), `SIGNER_FLAGS=` (comma list: `teach,llm,question,reply_stt`).

## 10. Python package
`core/pyproject.toml` (M0.3): package `signer_core`, Python ≥ 3.10 (mediapipe wheels decide: use a `core/.venv` with 3.12 if 3.13 has none), deps `mediapipe opencv-python fastapi uvicorn[standard] numpy httpx anthropic`, extra `dev` = `pytest`. Install: `python -m pip install -e "core[dev]"`. Run: `python -m signer_core.relay` (serves on `SIGNER_PORT`). Tests: `python -m pytest core/tests -q` — tests never need a camera, glasses or network (use `contracts/events.example.jsonl` and generated landmark arrays).

## 12. Clip-translate path (contract change 2026-11-13, lead; challenge/prompts/OBJECTIVE.md, directive 14)
The demo path is now **record a clip → upload → translate → text + audio**. The WS stream (§2–4) stays as a fallback, unchanged.
Flow: Neural Band pinch on the focused **Record** button in the glasses Web App → `POST /capture/start {"by":"hud"}` → core broadcasts `{"type":"capture","state":"recording","capture_id":"k1","ts":<ms>}` → the iOS app (DAT camera) records an MP4 → pinch **Stop** → `POST /capture/stop {"by":"hud"}` → broadcast `capture` `processing` → the iOS app POSTs the clip to `/translate` with `capture_id` → the core broadcasts the `caption` (with `audio_url`) and `capture` `idle`. A Web App has no camera (Meta FAQ), so the clip always comes from the iOS app, or in dev from a laptop webcam page / a file.

| Method + path | Request | Response |
|---|---|---|
| `POST /translate` | multipart: `video` (mp4/mov/webm, ≤ 30 s, ≤ 50 MB), optional `capture_id`, optional `speak` (default `true`) | `Translation` below; 413 too big, 415 undecodable |
| `POST /capture/start` | `{"by":"hud"|"card"|"app"}` | `{"capture_id":"k1","state":"recording"}`; also starts the consent session if it is off |
| `POST /capture/stop` | `{"by":"hud"|"card"|"app"}` | `{"capture_id":"k1","state":"processing"}` |
| `GET /audio/{id}.wav` | — | `audio/wav` (kept in RAM, last 20) |

`Translation` = `{"id":"c42","glosses":[{"gloss":"HELLO","confidence":0.91,"tier":"confirmed","t0_ms":0,"t1_ms":900}],"rejected":[{"gloss":"WATER","confidence":0.31}],"text":"Hello!","tier":"confirmed"|"unsure"|"none","alternatives":[…as §4],"mode":"gemini"|"template","audio_url":"/audio/c42.wav"|null,"tts":"gemini"|"none","timings_ms":{"decode":0,"landmarks":0,"classify":0,"translate":0,"tts":0,"total":0}}`. The same object is broadcast on `/ws/events` as a `caption` event (§4 fields plus `glosses`, `rejected`, `audio_url`, `tts`; `type:"caption"`).

Rules:
- Only `confirmed` and `unsure` glosses go to Gemini; `none`-tier ones go to `rejected` and are never sent. The prompt forbids adding content words that aren't in the glosses; the reply is checked against an allowlist built from the glosses' English and function words, and falls back to the template on failure. Unsure glosses are marked so the text can show them as uncertain. All rejected → `text:"Didn't catch that"`, tier `none`, no audio.
- Text: Gemini Flash, `SIGNER_GEMINI_MODEL` (confirm the current id on the AI Studio models page; the crew found `gemini-3.8-flash`). TTS: `SIGNER_TTS_MODEL` (found `gemini-3.8-flash-tts`), WAV 24 kHz mono. Key `GEMINI_API_KEY`. No key or network → `mode:"template"`, `tts:"none"`, and clients speak with `speechSynthesis`. Only gloss text is ever sent to Google, never video or landmarks.
- Video: `cv2.VideoCapture` on a temp file deleted right after decoding; frames → `signer_core.vision` Holistic → `signer_core.model` → segments. Nothing is stored.
- Model interface (M2.2 owns it): `signer_core.model.registry.load(name=os.environ.get("SIGNER_MODEL","knn"))` returns an object with `predict(features) -> list[tuple[str, float]]` (the interface `recognizer.classify` already uses); `signer_core.model.recognize_clip(xyz (T,75,3), t_ms (T,), classifier) -> list[Prediction]` segments a whole clip. Until it lands, the backend uses `Recognizer.push` + `flush`.
- Vocabulary: cut to ≤ 20 signs + REST by `SIGNER_VOCAB` (comma list, M2.2 picks it from `eval/results/m1.json`); `data/VOCAB.md` is updated with the final list.
- Env additions: `GEMINI_API_KEY=`, `SIGNER_GEMINI_MODEL=gemini-3.8-flash`, `SIGNER_TTS_MODEL=gemini-3.8-flash-tts`, `SIGNER_TTS_VOICE=`, `SIGNER_VOCAB=`. `SIGNER_MODEL` gains `lstm`. Python deps add `google-genai python-multipart`; extra `ml` = `torch` (CPU).

## 11. Asset specs
| Asset | Path | Spec |
|---|---|---|
| Deck | `deck/signer.pdf` (+ source `deck/index.html` or `.md`) | 8–10 slides 16:9, ≤ 15 MB, numbers only from `eval/results/*.json`, credits PopSign v1.0 (CC BY 4.0) |
| Demo video | `video/out/demo.mp4` | 60–90 s, 1920×1080, H.264 + AAC, −16 LUFS, ≤ 100 MB; user's global video rules (confirm voice first, no Eric) |
| Eval chart | `eval/results/final.png` | 1600×900 PNG from `eval/run.py --report` |
| Live-demo kit | `demo/consent-sign.pdf`, `demo/volunteer-consent.md`, `demo/script.md`, `demo/rehearsals.md` | A4, readable at 2 m |
| Evidence | `.hackforge/evidence/` | screenshots `.png`, `M0-spike.md`, `M0-bench.json` `{"fps":…,"source":"webcam"}`, `M2-latency.log` (one `sign_end_to_lens_ms=<n>` per line); no video of people |
| Card fonts | `card/fonts/*.woff2` | Figtree + Noto Sans latin subset, ≤ 120 KB total |
