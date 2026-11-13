"""Dev-only mock of the relay for the Signer Card (screenshots, manual testing). NOT the real core.

Serves card/ at GET / and implements the contract shapes the card uses (CONTRACTS §2, §4) in memory:
/session, /feedback, /reply, /teach, /ws/events, plus dev triggers:
  POST /dev/event            body = any event JSON, broadcast on /ws/events (and stored as current state for `state`)
  POST /dev/down?seconds=8   close every socket and refuse new ones for that long (simulates core down)
  POST /dev/reset            clear captions, replies, teach list, counters
  POST /dev/teach_rep?gloss=X  count one captured rep for a taught sign

Run:  PYTHONPATH=core core/.venv/bin/python card/dev/mock_server.py --port 8010
Needs fastapi + uvicorn (the core venv has them). Captions here are scripted, not recognised from video.
"""
import argparse
import json
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

CARD = Path(__file__).resolve().parents[1]
app = FastAPI(title="signer card mock")

S = {
    "state": "off", "link": "ok", "since": 0, "confirmed": 0, "total": 0, "captions": {}, "taught": {},
    "down_until": 0.0, "teach_n": 0,
}
sockets: set = set()


def now_ms() -> int:
    return int(time.time() * 1000)


def session() -> dict:
    on = S["state"] in ("on", "paused")
    return {"session_id": "s1" if on else None, "state": "on" if on else "off", "since": S["since"], "by": "card"}


async def broadcast(ev: dict) -> None:
    dead = []
    for ws in list(sockets):
        try:
            await ws.send_text(json.dumps(ev))
        except Exception:
            dead.append(ws)
    for ws in dead:
        sockets.discard(ws)


def state_event() -> dict:
    return {"type": "state", "state": S["state"], "link": S["link"], "ts": now_ms()}


@app.middleware("http")
async def maybe_down(request: Request, call_next):
    if time.time() < S["down_until"] and not request.url.path.startswith("/dev/"):
        return JSONResponse({"error": "down"}, status_code=503)
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0-mock", "model": "knn", "vocab": 24, "session": session()["state"]}


@app.get("/session")
def get_session():
    return session()


@app.post("/session/start")
async def start(body: dict):
    S.update(state="on", since=now_ms())
    await broadcast(state_event())
    return session()


@app.post("/session/stop")
async def stop(body: dict):
    S.update(state="off", since=now_ms())
    await broadcast(state_event())
    return session()


@app.post("/feedback")
async def feedback(body: dict):
    verdict = body.get("verdict")
    cid = body.get("caption_id")
    if verdict not in ("right", "wrong", "veto") or cid not in S["captions"]:
        raise HTTPException(422, "bad feedback")
    if S["captions"][cid] is None:  # first verdict for this caption counts toward the readout
        S["captions"][cid] = verdict
        S["total"] += 1
        S["confirmed"] += 1 if verdict == "right" else 0
    out = {"confirmed": S["confirmed"], "total": S["total"]}
    if verdict == "veto":
        await broadcast({"type": "retract", "id": cid})
    await broadcast({"type": "stats", **out})
    return out


@app.post("/reply")
async def reply(body: dict):
    text = str(body.get("text", "")).strip()
    if not text or body.get("source") not in ("stt", "typed"):
        raise HTTPException(422, "bad reply")
    await broadcast({"type": "reply", "text": text, "source": body["source"], "ts": now_ms()})
    return {"ok": True}


@app.post("/teach")
def teach(body: dict):
    gloss = str(body.get("gloss", "")).strip().upper()
    english = str(body.get("english", "")).strip()
    if not gloss or not english:
        raise HTTPException(422, "gloss and english required")
    S["teach_n"] += 1
    S["taught"][gloss] = {"gloss": gloss, "english": english, "reps": 0}
    return {"teach_id": f"t{S['teach_n']}", "reps_needed": 5}


@app.get("/teach")
def teach_list():
    return {"taught": list(S["taught"].values())}


@app.delete("/teach/{gloss}")
def teach_delete(gloss: str):
    return {"deleted": S["taught"].pop(gloss.upper(), None) is not None}


@app.post("/dev/teach_rep")
def dev_rep(gloss: str):
    if gloss in S["taught"]:
        S["taught"][gloss]["reps"] += 1
    return S["taught"].get(gloss, {})


@app.post("/dev/event")
async def dev_event(ev: dict):
    if ev.get("type") == "state":
        S.update(state=ev["state"], link=ev.get("link", "ok"))
    if ev.get("type") == "stats":
        S.update(confirmed=ev["confirmed"], total=ev["total"])
    if ev.get("type") == "caption":
        S["captions"][ev["id"]] = None
    ev.setdefault("ts", now_ms())
    await broadcast(ev)
    return {"ok": True}


@app.post("/dev/down")
async def dev_down(seconds: float = 8.0):
    S["down_until"] = time.time() + seconds
    for ws in list(sockets):
        await ws.close()
    sockets.clear()
    return {"down_for": seconds}


@app.post("/dev/reset")
async def dev_reset():
    S.update(state="off", link="ok", confirmed=0, total=0, captions={}, taught={})
    return {"ok": True}


@app.websocket("/ws/events")
async def events(ws: WebSocket):
    if time.time() < S["down_until"]:
        await ws.close(code=1013)
        return
    await ws.accept()
    sockets.add(ws)
    await ws.send_text(json.dumps(state_event()))
    await ws.send_text(json.dumps({"type": "stats", "confirmed": S["confirmed"], "total": S["total"]}))
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("type") == "reply" and msg.get("text"):
                await broadcast({"type": "reply", "text": msg["text"], "source": msg.get("source", "typed"), "ts": now_ms()})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        sockets.discard(ws)


@app.get("/")
def index():
    return FileResponse(CARD / "index.html")


app.mount("/", StaticFiles(directory=CARD), name="card")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8010)
    p.add_argument("--host", default="127.0.0.1")
    a = p.parse_args()
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
