# Gap check: backend, Gemini, TTS vs OBJECTIVE (m-8880b)

Scope: OBJECTIVE.md §2 (backend), §4 (translation), §5 (TTS), §6 (hosting) and the engineering constraints, checked against `core/`. Read-only on code. Dated 2026-11-13.

**Headline.** The relay is a *streaming* design: WS frames in, WS caption events out, with a consent session. It has **no REST upload/translate endpoint, no Gemini, no server-side TTS and no audio path**. Recognition and the template English exist and work. About 8–10 h of backend work gets the OBJECTIVE flow, and most of it is glue around existing modules. `pyproject.toml` and the contract still name Anthropic/Haiku, which the objective replaces with Gemini.

## 1. Gap table

| # | OBJECTIVE point | Status | Evidence |
|---|---|---|---|
| 2.1 | Python 3.11+ | MATCHES | `core/pyproject.toml:9` `requires-python = ">=3.11,<3.13"`. Note: the checked-in `core/.venv` is `python3.14` (`core/.venv/bin/pip3.14`), which the pin forbids. Rebuild it with 3.12 before the demo. |
| 2.2 | FastAPI | MATCHES | `relay/app.py:20,228` (`create_app`), `__main__.py` runs uvicorn |
| 2.3 | REST video upload + translation request | **MISSING** | The only REST routes are `/health, /vocab, /session*, /feedback, /reply` (`app.py:250-292`). Video enters only as JPEG frames over `WS /ws/frames` (`app.py:312-360`). There is no `UploadFile`, and `python-multipart` is not a dependency. |
| 2.4 | No streaming unless necessary | **PARTIAL (contradicts)** | The whole relay (CONTRACTS §2–4) is streaming: `/ws/frames` and `/ws/events`, with phrase gap and idle timers in `pipeline.py:54-106`. The objective wants record, stop, upload, one response. |
| 2.5 | OpenCV decode + frame extraction | PARTIAL | `cv2.imdecode` of single JPEGs, with rotation, in `pipeline.py:28-38`. **No `cv2.VideoCapture` / video-file path.** Offline clips go through `vision/clip.py` (landmarks `.npz`), not video. Needs a ~25-line `iter_frames(path)`. |
| 3 | MediaPipe → classifier | PARTIAL (out of scope here, noted) | `vision/holistic.py` is real. The classifier is **kNN** (`model/knn.py`), not PyTorch LSTM. The objective allows a pretrained model or dataset first, so kNN on PopSign landmarks is defensible; record that decision. The face mesh is not stored (CONTRACTS §5, 75 points). |
| 4.1 | Gemini Flash glosses → natural English | **MISSING** | `language/__init__.py:1` says "SIGNER_LLM=haiku comes later". There is no LLM call anywhere in `core/signer_core` (grep for gemini/anthropic hits only a docstring and `pyproject.toml:17`). The only translation is the rule-based `language/template.py:102-130 to_english` (`mode:"template"`). |
| 4.2 | Context only from recognized signs; never guess unrecognized | PARTIAL | Already enforced in structure: `pipeline.py:85` drops `tier=="none"` signs before English, and the template never invents words (`template.py:5-7`). A Gemini call must keep this: pass only kept glosses, forbid additions, and validate the output (§3). |
| 4.3 | Low-confidence flagged, not passed as facts | PARTIAL | A tier (`confirmed/unsure/none`) is computed per caption (`pipeline.py:94`, thresholds in `contracts.tier_for`). It is the *min* over signs, so one weak sign flags the whole phrase, and unsure signs are still merged into the sentence text. The new response needs per-gloss confidence plus a `rejected` list and an `uncertain` flag, and unsure glosses should be shown marked, not folded in silently. |
| 5.1 | Gemini TTS | **MISSING** | No server TTS. TTS is the browser `speechSynthesis` in `hud-web` and `AVSpeechSynthesizer` in the iOS plan (CONTRACTS §7–8). |
| 5.2 | Return audio to frontend | **MISSING** | No audio field in any event or response (CONTRACTS §4 caption has `speak:true` only). |
| 5.3 | Browser audio playback | PARTIAL | Browser `speechSynthesis` exists in `hud-web`, but there is no `<audio>`/WAV playback of server audio. Not checked in this mission beyond CONTRACTS §7. |
| 6.1 | Local FastAPI | MATCHES | `python -m signer_core.relay` serves on `SIGNER_HOST:PORT` (CONTRACTS §9). |
| 6.2 | No DB / auth | PARTIAL | No DB, and there is a consent state machine (`relay/session.py`), not auth. `/session/start` is a consent gate for the old streaming design, which a one-shot upload would not need. |
| C1 | Modular recognizer | MATCHES | `Recognizer` and `Classifier` are separable (`model/recognizer.py`, `Pipeline.set_classifier` `pipeline.py:122`). |
| C2 | Avoid MCP/DB/streaming | PARTIAL | See 2.4. |
| C3 | Clearly indicate uncertain predictions | MATCHES | Tiers and alternatives (`pipeline.py:94-106`), amber "?" on the lens (DESIGN.md/CONTRACTS §7). |
| C4 | Preserve temporal info | MATCHES | Segmenter + 32-step resample (`model/segmenter.py`, CONTRACTS §5). |
| C5 | Works reliably in live demo | PARTIAL | Needs the offline fallback in §4 (no Gemini dependency today, so it is currently safe, and it must stay safe). |
| Env | Dependencies | PARTIAL | `pyproject.toml:17` lists `anthropic`, and `google-genai`, `python-multipart` are absent. CONTRACTS §9 env vars are `SIGNER_LLM=haiku`, `ANTHROPIC_API_KEY`. Both are contract text and need a recorded change. |

## 2. Current Google Gen AI SDK facts (sources)

Package `google-genai`, imported as `from google import genai`.

**Sources:** https://aistudio.google.com/docs/models (redirected from ai.google.dev/gemini-api/docs/models), https://aistudio.google.com/docs/speech-generation (redirected from ai.google.dev/gemini-api/docs/speech-generation), Context7 `/websites/deepwiki_googleapis_python-genai`. These page summaries were extracted by a small model via WebFetch, so re-confirm ids at the AI Studio models page before coding.

- **Flash text model id.** Docs list `gemini-3.8-flash` (Stable, successor to `gemini-3.6-flash`). Also stable: `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`. `gemini-2.5-flash` is deprecated (routes to `gemini-3.5-flash-lite` from 2026-12-01). `gemini-2.0-flash` is shut down. **Recommendation: `gemini-3.8-flash`, configurable via `SIGNER_GEMINI_MODEL`, with `gemini-3.6-flash` as the manual fallback.** Context7's code samples still show `gemini-2.5-flash`, so they are stale for the id.
- **TTS model ids.** `gemini-3.8-flash-tts` (flagship) and `gemini-3.8-flash-lite-tts` (cheap/fast). Legacy: `gemini-3.1-flash-tts-preview` (the page says to move to 3.8), and `gemini-2.5-flash-preview-tts` (API access limited to existing users). **Recommendation: `gemini-3.8-flash-lite-tts` for latency (short sentences), `gemini-3.8-flash-tts` if the voice quality matters.**
- **API key env var.** The SDK reads `GOOGLE_API_KEY`, or `GEMINI_API_KEY` as fallback (Context7/DeepWiki, priority in that order). The speech page's REST example uses `$GEMINI_API_KEY`. **Use `GEMINI_API_KEY` and let `genai.Client()` pick it up.** If both are set, `GOOGLE_API_KEY` wins, which is a classic demo-day surprise.
- **Text call shape** (structured output):
  ```python
  from google import genai
  from google.genai import types
  client = genai.Client()                       # reads GEMINI_API_KEY
  r = client.models.generate_content(
      model="gemini-3.8-flash",
      contents=prompt,
      config=types.GenerateContentConfig(
          system_instruction=SYSTEM,
          temperature=0,
          response_mime_type="application/json",
          response_json_schema=SCHEMA),
  )
  data = json.loads(r.text)
  ```
  (shape from Context7 `generate_content` + `response_json_schema` example.) For hard timeouts use the SDK's `http_options` timeout, and wrap in `asyncio.wait_for` as a second guard.
- **TTS call shape (current docs).** The speech page requires `google-genai >= 2.25.0` and uses the *Interactions* API:
  ```python
  client = genai.Client(http_options={"api_version": "v1beta"})
  i = client.interactions.create(
      model="gemini-3.8-flash-tts",
      input=[{"type":"user_input","content":[{"type":"text","text":"Please wait."}]}],
      response_format={"type":"audio"},
      generation_config={"speech_config":[{"voice":"Kore"}]})
  wav_bytes = base64.b64decode(i.output_audio.data)
  ```
- **Audio format.** Unary requests return **WAV with a RIFF header, 24 kHz, mono, 16-bit little-endian PCM** (`audio/wav`), so the bytes can be served as-is (`Response(wav, media_type="audio/wav")`). Only *streaming* returns headerless PCM (`audio/l16`, same params), which would need wrapping:
  ```python
  import wave
  with wave.open(buf, "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
  ```
  **Not verified:** the older `generate_content` + `response_modalities=["AUDIO"]` + `speech_config` route (what most tutorials and the 2.5 TTS models used, returning raw PCM in `inline_data`) may or may not still work for 3.8 models. The fetched pages did not confirm it. The first spike task is one real call to confirm which route returns playable audio, and the code must check `data[:4] == b"RIFF"` and wrap if not.
- Voices: 30 prebuilt, e.g. `Kore` (used in docs).

## 3. Smallest design

### Endpoint

`POST /translate` (multipart: `video` file, ~≤10 s clip, webm/mp4/mov; optional `tts=true|false`, default true). `GET /audio/{id}.wav` serves the cached WAV (in-memory dict with ~20-entry LRU, no DB). Alternative: inline `audio_b64`, which is simpler for the Web App and avoids a second fetch; recommend **inline base64 `audio_wav_b64`** (24 kHz mono, ~100–200 KB for a short sentence), with `audio_url` left out.

Response:
```json
{"glosses":[{"gloss":"HELLO","confidence":0.91,"tier":"confirmed","start_ms":120,"end_ms":640}],
 "rejected":[{"gloss":"WATER","confidence":0.31,"reason":"below_threshold"}],
 "english":"Hello, can I ask a question?",
 "uncertain":false,
 "mode":"llm"|"template",
 "audio":{"format":"wav","sample_rate":24000,"b64":"…"}|null,
 "tts":"gemini"|"browser",
 "notes":[],"timings_ms":{"decode":0,"landmarks":0,"classify":0,"llm":0,"tts":0}}
```
`rejected` = segments with tier `none`; they are **not** sent to Gemini and are never in `english`. `uncertain` is true when any kept gloss is `unsure` or nothing was recognised (then `english` = "Didn't catch that" and no audio is generated, and the frontend must not speak it as a translation).

### Pipeline (all existing modules)

1. `iter_frames(path)` with `cv2.VideoCapture` (new, ~25 lines; honour rotation metadata, subsample to ~15 fps, cap duration/size). Write the upload to a temp file because OpenCV needs a path. Delete it right after.
2. For each frame: `JpegLandmarker.landmarks(frame, ts)` (existing, `pipeline.py:40`) → `Recognizer.push(f75, ts)` (existing) → `flush()` at the end. Run this synchronously in a threadpool (`asyncio.to_thread`). No `Pipeline`/`PhraseBuilder` timers needed. Group predictions in one pass.
3. Split kept vs rejected by `contracts.tier_for`.
4. **Gemini translate** (`language/gemini.py`, ~60 lines): the system prompt says "You receive an ordered list of ASL glosses that a recognizer identified. Write one short natural English sentence. Use ONLY these glosses. Do not add facts, names, or objects. Do not guess missing signs. If unsure, output the glosses as plain words." Input is the gloss list with display English from `VOCAB.md` (never confidences or rejected ones). Use JSON schema `{english: string}`, `temperature=0`, ~4 s timeout.
5. **Guardrail (cheap, important for "never invent"):** accept the LLM sentence only if every content word in it is either from the kept glosses' English, in a small function-word allowlist (a, the, is, I, you, can, please, …), or inflection of those. If the check fails or the call errors, use `to_english()` (template). This makes the "only recognized glosses" rule verifiable rather than prompt-only, and tests can assert it.
6. **Gemini TTS** for `english` unless `uncertain`; returns WAV. On any error, `audio:null, tts:"browser"`.
7. Return JSON. Log timings (reuse `M2-latency.log` format if needed).

### Keep from the relay
- `JpegLandmarker`, `Recognizer`, classifier loading (`ensure_model`), tiers, `to_english` template, `read_english`/`VOCAB.md`, `/health`, `/vocab`, static serving of the frontend, `python -m signer_core.relay` entry.
- Consent: **keep as a UI concept, drop as server gating.** Under the objective the user starts/stops capture with a Neural Band gesture and the video is uploaded explicitly. The upload is the consent act. Keep "frames are never persisted" (delete the temp file, log no video) and keep `Session` + the card only if the iOS/Web App path still streams.
- The card (`card/`) can stay for the dev/streaming path and for showing the demo.

### Drop or leave dormant (do not delete without the lead's decision)
`/ws/frames`, `/ws/events`, `PhraseBuilder` timers, idle-stop, link-slow stats, `/feedback`, `/reply`, `/teach`. They are working and tested (`core/tests/test_relay.py`, 12 tests), so leaving them is cheaper than removing them. Directive 14 says OBJECTIVE is the target. The lead decides whether the streaming glasses-app path stays as a stretch feature.

### Offline / failure fallback (so the live demo can't die)
Layered, each layer independent and reported in the response:
1. No `GEMINI_API_KEY`, network down, timeout (≤4 s) or guardrail rejection → `mode:"template"` English from `to_english` (already tested, `test_template_english`). `notes:["gemini_unavailable"]`.
2. TTS failure/missing key → `audio:null, tts:"browser"`; the Web App calls `speechSynthesis` on `english` (already implemented in `hud-web` per CONTRACTS §7).
3. **Demo-day cache:** an optional `data/demo_cache.json` mapping a gloss tuple → `{english, wav_b64}` pre-generated for the ~10 demo phrases while online (`python -m signer_core.tools.warm_cache`). Checked before Gemini, so the common phrases replay instantly with no network. Cache keys must be exact gloss tuples, so it never answers for unrecognised content.
4. A `GET /health` field `gemini: "ok"|"no_key"|"unreachable"` (check by key presence, not by a live call) so the card shows which path is live before the demo starts.
5. `SIGNER_LLM=off` env forces template mode (this already exists in the contract, rename values to `off|gemini`).

### Contract/config changes needed (lead must record in STATE.md, frozen)
- CONTRACTS §2 add `POST /translate`; §9 replace `SIGNER_LLM=haiku`, `SIGNER_LLM_MODEL`, `ANTHROPIC_API_KEY` with `SIGNER_LLM=off|gemini`, `SIGNER_GEMINI_MODEL=gemini-3.8-flash`, `SIGNER_TTS_MODEL=gemini-3.8-flash-lite-tts`, `SIGNER_TTS_VOICE=Kore`, `GEMINI_API_KEY`; §10 dependencies: `google-genai>=2.25`, `python-multipart`, drop `anthropic`.
- `core/pyproject.toml` is shared (M1 owns `core/signer_core/relay/**`, `language/**`). A new `relay/translate.py` and `language/gemini.py` fit those owned paths. `pyproject.toml` and CONTRACTS edits are shared files.
- Egress note: R3/DECISION data practice says only gloss text leaves the machine. Gemini calls send gloss/English text only (never video or landmarks), which stays consistent. TTS sends only the English sentence.

## 4. Hour estimates

| Task | h |
|---|---|
| Spike: one real `generate_content` + one TTS call, confirm model ids, route and WAV header (needs a key, Python 3.12 venv, `pip install google-genai`) | 0.75 |
| `iter_frames` + `POST /translate` (multipart, size/duration limits, temp-file cleanup, threadpool) | 2 |
| Recognise a whole clip: flush, kept/rejected split, per-gloss start/end/confidence output | 1.5 |
| `language/gemini.py`: prompt, schema, timeout, **word-guardrail**, fallback to template | 2 |
| TTS wrapper (WAV passthrough or wrap PCM), base64 response, error → browser fallback | 1 |
| Demo cache + warm script, `/health` gemini field | 1 |
| Tests (mocked Gemini: success, timeout, guardrail reject, no key, rejected glosses never sent; upload test with a tiny synthetic mp4) | 1.5 |
| Contract/env/pyproject updates + README run notes | 0.5 |
| **Total backend** | **≈ 10 h** (≈ 7 h with the cache and `/health` field cut) |

Out of this mission (frontend/device): Web App record → upload → render → `<audio>` playback (~2–3 h), and verifying real glasses-camera/Neural Band access, which OBJECTIVE §1 itself flags as unverified.

## 5. Risks and unknowns
- **TTS route not verified for 3.8 models** with the older `generate_content` call (see §2). Mitigated by the spike plus a RIFF-header check.
- Model ids change fast (2.5-flash deprecated, 3.1 preview legacy). Keep them in env vars. Do not hard-code them.
- Latency: classify + Gemini (~1 s) + TTS (~1–3 s, unmeasured) on top of landmarks. Measure in the spike. The cache covers the demo phrases.
- A recorded clip from glasses may be portrait 504×896, so rotate with the header or container metadata. `JpegLandmarker` already supports `rot`.
- `core/.venv` is Python 3.14, but mediapipe wheels need ≤3.12 (`pyproject.toml:9`). Rebuild before running any of this.
- Directive 14 vs the existing M1/M2 streaming work: the lead should decide whether `/translate` replaces or sits beside the WS path. This report assumes beside (cheapest).
