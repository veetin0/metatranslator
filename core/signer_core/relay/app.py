"""Relay: FastAPI app (CONTRACTS §2-4). `signer_core.relay.app:app`, or `create_app(...)` for tests.

    python -m signer_core.relay                 # serves on SIGNER_HOST:SIGNER_PORT (0.0.0.0:8000)

Frames arrive on /ws/frames only while the session is `on` (else WS close 4403 consent_required); each is
decoded, turned into landmarks and dropped. Events fan out on /ws/events to the app, the card and the hud.
The classifier is fitted lazily on the first Start (SIGNER_DATA_DIR clips), so /health never waits for it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import statistics
import time
from collections import deque
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..contracts import REST, VERSION, unpack_frame
from ..language import read_english
from .pipeline import Pipeline
from .session import SessionManager, now_ms

log = logging.getLogger("signer.relay")

REPO = Path(__file__).resolve().parents[3]
MAX_FRAME_AGE_MS = 300
ACK_EVERY = 30
CLOSE_CONSENT = 4403


class StartBody(BaseModel):
    by: str = "card"


class StopBody(BaseModel):
    by: str = "card"


class FeedbackBody(BaseModel):
    caption_id: str
    verdict: str


class ReplyBody(BaseModel):
    text: str
    source: str = "typed"


FALLBACK_CARD = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Signer Card</title></head>
<body style="font:18px system-ui;background:#0b0f14;color:#e8edf2;padding:24px">
<h1>Signer</h1><p>card/ is not built yet: this is the relay's minimal consent page.</p>
<p><button id="start" style="font-size:24px">Start</button> <button id="stop" style="font-size:24px">Stop</button></p>
<p id="state">off</p><ol id="log"></ol>
<script>
const post=(p,b)=>fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})
 .then(r=>r.json()).then(s=>document.getElementById('state').textContent=s.state);
document.getElementById('start').onclick=()=>post('/session/start',{by:'card'});
document.getElementById('stop').onclick=()=>post('/session/stop',{by:'card'});
const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws/events');
ws.onopen=()=>ws.send(JSON.stringify({type:'hello',client:'card'}));
ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.type==='state')document.getElementById('state').textContent=m.state;
 if(m.type==='caption'){const li=document.createElement('li');li.textContent=m.text+' ('+m.tier+')';
 document.getElementById('log').prepend(li);}};
</script></body></html>"""


class Hub:
    """Connected /ws/events clients; broadcast never raises (dead sockets are dropped)."""

    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def send(self, ws: WebSocket, event: dict) -> bool:
        try:
            await ws.send_text(json.dumps(event, separators=(",", ":")))
            return True
        except Exception:  # noqa: BLE001 - a client vanished mid-send
            self.clients.discard(ws)
            return False

    async def broadcast(self, event: dict) -> None:
        for ws in list(self.clients):
            await self.send(ws, event)


class Relay:
    def __init__(self, classifier=None, landmarker=None, data_dir: str | None = None,
                 idle_stop_s: float | None = None, phrase_gap_ms: int = 1200, clock=time.monotonic):
        self.data_dir = data_dir or os.environ.get("SIGNER_DATA_DIR", str(REPO / "data"))
        self.model_name = os.environ.get("SIGNER_MODEL", "knn")
        self.english = read_english(Path(self.data_dir) / "VOCAB.md")
        kw = {} if idle_stop_s is None else {"idle_stop_s": idle_stop_s}
        self.session = SessionManager(clock=clock, **kw)
        self.pipeline = Pipeline(classifier, landmarker, self.english, phrase_gap_ms, on_segment=self.session.touch)
        self.hub = Hub()
        self.frame_sockets: set[WebSocket] = set()
        self.captions: dict[str, dict] = {}
        self.verdicts = {"confirmed": 0, "total": 0}
        self.link = "ok"
        self._ages: deque = deque()
        self._model_lock = asyncio.Lock()
        self._model_task: asyncio.Task | None = None
        self.model_error: str | None = None

    # -- model -------------------------------------------------------------------------------------------
    def vocab(self) -> list[dict]:
        from ..model import read_vocab

        path = Path(self.data_dir) / "VOCAB.md"
        rows = []
        if path.exists():
            glosses = set(read_vocab(path)) - {REST}
            for line in path.read_text(encoding="utf-8").splitlines():
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) >= 3 and cells[0] in glosses:
                    rows.append({"gloss": cells[0], "english": cells[1], "source": cells[2]})
        return rows

    async def ensure_model(self) -> None:
        if self.pipeline.classifier is not None:
            return
        async with self._model_lock:
            if self.pipeline.classifier is not None:
                return
            from ..model import build_classifier

            try:
                clf = await asyncio.to_thread(build_classifier, self.data_dir)
            except FileNotFoundError as e:  # no clips yet: frames are accepted, no captions until data exists
                self.model_error = str(e)
                log.warning("model not loaded: %s", e)
                return
            self.pipeline.set_classifier(clf)
            self.model_error = None
            log.info("model %s fitted: %d classes", self.model_name, len(clf.classes))

    # -- session -----------------------------------------------------------------------------------------
    def state_event(self) -> dict:
        return {"type": "state", "state": self.session.state, "link": self.link, "ts": now_ms()}

    async def start(self, by: str) -> dict:
        snap = self.session.start(by)
        await self.hub.broadcast(self.state_event())
        if self.pipeline.classifier is None and self._model_task is None:  # fit in the background, Start stays fast
            self._model_task = asyncio.create_task(self.ensure_model())
            self._model_task.add_done_callback(lambda _t: setattr(self, "_model_task", None))
        return snap

    async def stop(self, by: str) -> dict:
        snap = self.session.stop(by)
        self.pipeline.reset()  # consent withdrawn: nothing in flight is emitted
        for ws in list(self.frame_sockets):
            try:
                await ws.close(code=CLOSE_CONSENT, reason="consent_required")
            except Exception:  # noqa: BLE001
                pass
        self.frame_sockets.clear()
        await self.hub.broadcast(self.state_event())
        return snap

    async def check_idle(self) -> None:
        if self.session.idle_expired():
            log.info("idle stop after %.0f s without a segment", self.session.idle_stop_s)
            await self.stop("idle")

    # -- events ------------------------------------------------------------------------------------------
    async def emit(self, events: list[dict]) -> None:
        for ev in events:
            if ev["type"] == "caption":
                self.captions[ev["id"]] = ev
                while len(self.captions) > 200:
                    self.captions.pop(next(iter(self.captions)))
            await self.hub.broadcast(ev)

    async def feedback(self, caption_id: str, verdict: str) -> dict:
        if verdict not in ("right", "wrong", "veto"):
            raise ValueError("verdict must be right, wrong or veto")
        if caption_id not in self.captions:
            raise KeyError(caption_id)
        self.verdicts["total"] += 1
        self.verdicts["confirmed"] += verdict == "right"
        if verdict == "veto":
            await self.hub.broadcast({"type": "retract", "id": caption_id})
        stats = dict(self.verdicts)
        await self.hub.broadcast({"type": "stats", **stats})
        return stats

    async def reply(self, text: str, source: str) -> None:
        if not text.strip():
            raise ValueError("text is empty")
        if source not in ("stt", "typed"):
            raise ValueError("source must be stt or typed")
        await self.hub.broadcast({"type": "reply", "text": text.strip(), "source": source, "ts": now_ms()})

    async def on_client_message(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "feedback":
            await self.feedback(str(msg.get("caption_id", "")), str(msg.get("verdict", "")))
        elif kind == "reply":
            await self.reply(str(msg.get("text", "")), str(msg.get("source", "typed")))

    # -- frames ------------------------------------------------------------------------------------------
    def frame_age_ok(self, ts_ms: int) -> bool:
        """Drop stale frames (> 300 ms) when the producer stamps wall-clock time; track link quality."""
        if ts_ms < 10**12:  # relative clock (webcam / mock): age unknown, accept
            return True
        now = now_ms()
        age = now - ts_ms
        self._ages.append((now, age))
        while self._ages and now - self._ages[0][0] > 3000:
            self._ages.popleft()
        return age <= MAX_FRAME_AGE_MS

    def link_changed(self) -> bool:
        link = "slow" if self._ages and statistics.median(a for _, a in self._ages) > MAX_FRAME_AGE_MS else "ok"
        changed, self.link = link != self.link, link
        return changed


def create_app(classifier=None, landmarker=None, data_dir: str | None = None, card_dir: str | None = None,
               idle_stop_s: float | None = None, phrase_gap_ms: int = 1200, clock=time.monotonic) -> FastAPI:
    relay = Relay(classifier, landmarker, data_dir, idle_stop_s, phrase_gap_ms, clock)

    async def lifespan(app):
        async def idle_loop():
            while True:
                await asyncio.sleep(1.0)
                await relay.check_idle()

        task = asyncio.create_task(idle_loop())
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(title="Signer relay", version=VERSION, lifespan=lifespan)
    app.state.relay = relay

    def bad(status: int, error: str):
        return JSONResponse({"error": error}, status_code=status)

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": VERSION, "model": relay.model_name, "vocab": len(relay.vocab()),
                "session": relay.session.state}

    @app.get("/vocab")
    async def vocab():
        return {"signs": relay.vocab()}

    @app.get("/session")
    async def get_session():
        return relay.session.snapshot()

    @app.post("/session/start")
    async def start(body: StartBody | None = None):
        try:
            return await relay.start((body or StartBody()).by)
        except ValueError as e:
            return bad(422, str(e))

    @app.post("/session/stop")
    async def stop(body: StopBody | None = None):
        try:
            return await relay.stop((body or StopBody()).by)
        except ValueError as e:
            return bad(422, str(e))

    @app.post("/feedback")
    async def feedback(body: FeedbackBody):
        try:
            return await relay.feedback(body.caption_id, body.verdict)
        except KeyError:
            return bad(404, "unknown_caption")
        except ValueError as e:
            return bad(422, str(e))

    @app.post("/reply")
    async def reply(body: ReplyBody):
        try:
            await relay.reply(body.text, body.source)
        except ValueError as e:
            return bad(422, str(e))
        return {"ok": True}

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket):
        await ws.accept()
        relay.hub.clients.add(ws)
        await relay.hub.send(ws, relay.state_event())
        await relay.hub.send(ws, {"type": "stats", **relay.verdicts})
        try:
            while True:
                try:
                    msg = json.loads(await ws.receive_text())
                    await relay.on_client_message(msg if isinstance(msg, dict) else {})
                except (ValueError, KeyError) as e:
                    log.info("ignored client message: %s", e)
        except WebSocketDisconnect:
            pass
        finally:
            relay.hub.clients.discard(ws)

    @app.websocket("/ws/frames")
    async def ws_frames(ws: WebSocket):
        await ws.accept()
        if not relay.session.is_on:
            await ws.close(code=CLOSE_CONSENT, reason="consent_required")
            return
        relay.frame_sockets.add(ws)
        n = 0
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                data = msg.get("bytes")
                if data is None:
                    continue
                if not relay.session.is_on:
                    await ws.close(code=CLOSE_CONSENT, reason="consent_required")
                    break
                try:
                    header, jpeg = unpack_frame(data)
                except Exception:  # noqa: BLE001 - malformed message: skip it
                    continue
                n += 1
                if n % ACK_EVERY == 0:
                    await ws.send_text(json.dumps({"type": "ack", "seq": header.get("seq", n)}))
                ok = relay.frame_age_ok(int(header.get("ts_ms", 0)))
                if relay.link_changed():
                    await relay.hub.broadcast(relay.state_event())
                if not ok:
                    continue
                try:
                    events = await asyncio.to_thread(relay.pipeline.push_jpeg, header, jpeg)
                except ValueError as e:
                    log.info("frame %s skipped: %s", header.get("seq"), e)
                    continue
                if relay.session.is_on:  # Stop may have landed while the frame was processed
                    await relay.emit(events)
                await relay.check_idle()
        except WebSocketDisconnect:
            pass
        finally:
            relay.frame_sockets.discard(ws)
            if relay.session.is_on:
                await relay.emit(relay.pipeline.flush())

    card = Path(card_dir or os.environ.get("SIGNER_CARD_DIR", str(REPO / "card")))
    if (card / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(card), html=True), name="card")
    else:
        @app.get("/", response_class=HTMLResponse)
        async def fallback_card():
            return FALLBACK_CARD

    return app


app = create_app()
