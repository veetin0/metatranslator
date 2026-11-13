# M3.4 Signer Card evidence (D6)

**These screenshots are from a mock event feed, not live recognition.** No camera, model or glasses were involved.
They were taken 2026-11-13 in Playwright Chromium at 390x844 against `card/dev/mock_server.py`, a dev-only stand-in for
the relay (stdlib-style FastAPI app, in-memory) that serves `card/` and answers `/session`, `/feedback`, `/reply`,
`/teach` with the CONTRACTS §2/§4 shapes, and pushes scripted events over `/ws/events`. The real relay endpoints
(`/teach`, `/feedback`) are built by other M3 tasks and were not available.

Run it: `PYTHONPATH=core core/.venv/bin/python card/dev/mock_server.py --port 8010`, then open `http://127.0.0.1:8010/`.
Dev-only triggers: `POST /dev/event` (broadcast any event), `POST /dev/down?seconds=N` (drop and refuse sockets),
`POST /dev/teach_rep?gloss=X`, `POST /dev/reset`.

| File | What it shows and how it was made |
|---|---|
| `M3-card-permission_denied.png` | Start pressed on the card, then a `state: permission_denied` event. Banner with lock icon, title and the next step; "Permission denied" chip. |
| `M3-card-glasses_off.png` | `state: glasses_off` event. Amber banner, glasses icon, next step; "Glasses off" chip. |
| `M3-card-core_down.png` | `POST /dev/down?seconds=14` drops the socket; the card itself shows "Core down" after 2 s without a socket (the core never sends it). The banner cleared on its own when the mock came back, which shows the auto-reconnect. |
| `M3-card-readout.png` | Mock seeded with 16 of 18, then a real click on **Right** on the latest caption: the card shows "17 of 19 confirmed right" (from the `/feedback` response and the `stats` event). Right / Wrong / "Not right, remove it" below. |
| `M3-card-reply.png` | A spoken-style `reply` event plus a reply typed into the fallback form (`POST /reply` with `source:"typed"`): large filled block for the newest reply, muted rows for older ones. Below, a vetoed unsure caption struck through with "Removed from the glasses." |
| `M3-card-teach.png` | Teach form, "Sign PROJECTOR 5 times" with 2 of 5 progress, and the taught list with one-tap Delete (a delete was clicked and works). |

Other checks: no console errors on load; no horizontal scroll at 320 px; every button and input is at least 44 px;
`design-scan` reports 0 findings (`M3-card-design-scan.json`); the QR encoder in `card/qr.js` was decoded back to the
exact URL with OpenCV's `QRCodeDetector` for four URLs (25 to 37 modules wide).
The "console errors" during the core_down screenshot are the browser's own WebSocket connection-refused messages,
expected while the mock is down.
