# M1 frontend evidence (D9)

All screenshots were taken 2026-11-13 on the lead's Mac with Playwright Chromium, against the real relay
(`hud-web/tools/replay_core.py`, which is `signer_core.relay.app.create_app()` plus a dev-only `POST /dev/replay`).

- Captions are **replayed** from `contracts/events.example.jsonl` through the relay's `/ws/events` fan-out after a real
  `POST /session/start`. They are not live recognition: no camera and no trained model were involved.
- The lens shots use a plain **600×600 browser viewport** serving `hud-web` (`vite preview`). The Meta Display Simulator
  extension was **not** used for these.

| File | How it was made |
|---|---|
| `M1-card-start.png` | Card at `http://127.0.0.1:8000/` (narrow viewport): Start pressed, then `replay?only=c1`. ON light, Stop only, latest caption ✓ sure. |
| `M1-sim-caption.png` | Lens at `http://127.0.0.1:4173/`, 600×600, after `replay?only=c1` (confirmed tier, white). |
| `M1-sim-unsure.png` | Same lens after `replay?only=c2&types=caption` (unsure tier: amber, "?" prefix, top alternative). |
| `M1-card-stop.png` | Card after `replay?only=c1`, then the Stop button clicked: Translation OFF, Start shown, the last caption kept. |

The readout shows "0/0 confirmed" because only caption events were replayed (no stats event and no feedback).

Bug found while capturing: in `hud-web/src/main.js`, speech ran before `paint()` inside the socket's try/catch, so a
speech-synthesis error dropped the caption. The fix paints first and wraps the speech call in its own try/catch.
