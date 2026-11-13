"""Idle auto-stop (CONTRACTS §2): the session goes `off` (by "idle") after SIGNER_IDLE_STOP_S without a segment.

Consent resets with it: the frame sockets are closed with 4403 and a new Start is needed. `0` turns it off.

    watcher = IdleWatcher(relay)            # relay.check_idle() every `interval` seconds
    await watcher.tick()                    # one check (tests drive this with a fake clock)
"""
from __future__ import annotations

import asyncio
import logging
import os

from ..contracts import IDLE_STOP_S

log = logging.getLogger("signer.idle")


def idle_stop_s(env=None) -> float:
    """SIGNER_IDLE_STOP_S read now (not at import), default 120; bad or negative values fall back to it."""
    raw = (os.environ if env is None else env).get("SIGNER_IDLE_STOP_S", "")
    try:
        v = float(raw)
    except ValueError:
        return float(IDLE_STOP_S)
    return v if v >= 0 else float(IDLE_STOP_S)


def seconds_left(session) -> float | None:
    """Seconds until the idle stop, or None when the session is off or idle stop is disabled."""
    if not session.is_on or session.idle_stop_s <= 0:
        return None
    return max(0.0, session.idle_stop_s - (session._clock() - session._last_activity))


class IdleWatcher:
    def __init__(self, relay, interval: float = 1.0):
        self.relay = relay
        self.interval = interval
        self._task: asyncio.Task | None = None

    async def tick(self) -> bool:
        """Stop the session if it has been idle too long; True if it was stopped now."""
        if self.relay.session.idle_expired():
            log.info("idle stop after %.0f s without a segment", self.relay.session.idle_stop_s)
            await self.relay.stop("idle")
            return True
        return False

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            try:
                await self.tick()
            except Exception:  # noqa: BLE001 - the watcher must outlive one bad stop
                log.exception("idle check failed")

    def start(self) -> asyncio.Task:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run())
        return self._task

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
