"""M3.3 D3: idle auto-stop after SIGNER_IDLE_STOP_S and consent reset (a new Start is always needed)."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from signer_core.model.teach import TeachStore
from signer_core.relay.app import create_app
from signer_core.relay.feedback import install
from signer_core.relay.idle import IdleWatcher, idle_stop_s, seconds_left
from test_model import body
from test_relay import classifier, fake_landmarker, frame_msg, recv_until  # noqa: F401 - fixture


def idle_client(classifier, tmp_path, monkeypatch, secs="5"):
    monkeypatch.setenv("SIGNER_IDLE_STOP_S", secs)
    t = [0.0]
    app = create_app(classifier=classifier, landmarker=fake_landmarker, idle_stop_s=idle_stop_s(),
                     clock=lambda: t[0], card_dir=str(tmp_path))
    store = install(app, app.state.relay, enabled=True, store=TeachStore(tmp_path / "taught"))
    return TestClient(app), app.state.relay, store, t


def test_idle_stop_s_reads_env_now():
    assert idle_stop_s({"SIGNER_IDLE_STOP_S": "7"}) == 7.0
    assert idle_stop_s({"SIGNER_IDLE_STOP_S": "0"}) == 0.0
    assert idle_stop_s({"SIGNER_IDLE_STOP_S": "soon"}) == 120.0
    assert idle_stop_s({"SIGNER_IDLE_STOP_S": "-3"}) == 120.0
    assert idle_stop_s({}) == 120.0


def test_idle_auto_stop_after_env_seconds_resets_consent(classifier, tmp_path, monkeypatch):
    client, relay, store, t = idle_client(classifier, tmp_path, monkeypatch)
    watcher = IdleWatcher(relay)
    assert client.post("/session/start", json={"by": "card"}).json()["session_id"] == "s1"
    client.post("/teach", json={"gloss": "LAMP", "english": "lamp"})
    with client.websocket_connect("/ws/events") as ev:
        ev.receive_text(), ev.receive_text()
        t[0] = 4.9
        assert seconds_left(relay.session) == pytest.approx(0.1)
        assert not ev.portal.call(watcher.tick)
        t[0] = 5.0
        assert ev.portal.call(watcher.tick)
        off = recv_until(ev, "state")
        assert off["state"] == "off"
    s = client.get("/session").json()
    assert s["state"] == "off" and s["by"] == "idle" and seconds_left(relay.session) is None
    assert store.active is None  # a teach in progress is cancelled with the consent
    with client.websocket_connect("/ws/frames") as ws:  # consent reset: frames refused until a new Start
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
    assert e.value.code == 4403
    assert client.post("/session/start", json={"by": "card"}).json()["session_id"] == "s2"


def test_segments_push_the_idle_stop_back(classifier, tmp_path, monkeypatch):
    client, relay, _, t = idle_client(classifier, tmp_path, monkeypatch)
    client.post("/session/start", json={"by": "card"})
    t[0] = 4.0
    relay.session.touch()  # what the pipeline does on every recognised segment
    t[0] = 8.0
    assert not asyncio.run(IdleWatcher(relay).tick()) and relay.session.is_on
    t[0] = 9.0
    assert asyncio.run(IdleWatcher(relay).tick()) and relay.session.snapshot()["by"] == "idle"


def test_idle_stop_zero_disables_it(classifier, tmp_path, monkeypatch):
    client, relay, _, t = idle_client(classifier, tmp_path, monkeypatch, secs="0")
    client.post("/session/start", json={"by": "card"})
    t[0] = 10_000.0
    assert not asyncio.run(IdleWatcher(relay).tick()) and relay.session.is_on


def test_watcher_loop_stops_the_session(classifier, tmp_path, monkeypatch):
    _, relay, _, t = idle_client(classifier, tmp_path, monkeypatch)

    async def run():
        relay.session.start("app")
        t[0] = 6.0
        w = IdleWatcher(relay, interval=0.01)
        w.start()
        for _ in range(100):
            if not relay.session.is_on:
                break
            await asyncio.sleep(0.01)
        w.stop()

    asyncio.run(run())
    assert relay.session.snapshot()["by"] == "idle"
    assert json.dumps(relay.session.snapshot())  # still a plain Session
