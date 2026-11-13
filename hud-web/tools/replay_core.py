"""Dev only: the real relay (consent, card at /, /ws/events, feedback) plus POST /dev/replay, which broadcasts the
caption/reply/stats events of contracts/events.example.jsonl as if recognised. For UI work and screenshots
without a camera or a trained model. Replay is refused while the session is off (the same consent rule as frames).

    core/.venv/bin/python hud-web/tools/replay_core.py [--port 8000]
    curl -X POST localhost:8000/dev/replay            # all events, 1.5 s apart
    curl -X POST 'localhost:8000/dev/replay?only=c1'  # one caption id (and its retract, if any)
    curl -X POST 'localhost:8000/dev/replay?only=c2&types=caption'  # the caption without its retract
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

# don't rely on the venv's editable .pth (macOS sometimes flags it hidden and Python 3.12 skips it)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "core"))

import uvicorn
from fastapi import HTTPException
from fastapi.routing import APIRoute

from signer_core.relay.app import create_app
from signer_core.relay.session import now_ms

EVENTS = Path(__file__).resolve().parents[2] / "contracts" / "events.example.jsonl"

app = create_app()
relay = app.state.relay


async def replay(only: str | None = None, types: str = "caption,retract,reply,stats", gap_s: float = 1.5):
    if not relay.session.is_on:
        raise HTTPException(409, {"error": "consent_required"})
    events = [json.loads(line) for line in EVENTS.read_text().splitlines() if line.strip()]
    keep = set(types.split(",")) & {"caption", "retract", "reply", "stats"}
    events = [e for e in events if e["type"] in keep]
    if only:
        events = [e for e in events if e.get("id") == only]
    for i, ev in enumerate(events):
        if i:
            await asyncio.sleep(gap_s)
        await relay.emit([{**ev, "ts": now_ms()} if "ts" in ev else ev])
    return {"replayed": len(events)}


# the card is mounted at "/", so the dev route must come first
app.router.routes.insert(0, APIRoute("/dev/replay", replay, methods=["POST"]))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
