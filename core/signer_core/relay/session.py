"""Consent / session state machine (CONTRACTS §2): Start *is* consent; Stop, idle and device STOPPED reset it.

off --start--> on --stop(card|app|idle|device)--> off. A new Start is always needed after any stop, so no
frame is ever processed without a live consent. `paused` is reserved for the app (glasses doffed) and is not
reachable from the M1 endpoints.
"""
from __future__ import annotations

import threading
import time

from ..contracts import IDLE_STOP_S, Session

STOP_REASONS = ("card", "app", "idle", "device")
START_BY = ("card", "app")


def now_ms() -> int:
    return int(time.time() * 1000)


class SessionManager:
    def __init__(self, idle_stop_s: float = IDLE_STOP_S, clock=time.monotonic):
        self.idle_stop_s = idle_stop_s
        self._clock = clock
        self._lock = threading.Lock()
        self._n = 0
        self._id: str | None = None
        self._state = "off"
        self._since = now_ms()
        self._by = "card"
        self._last_activity = clock()

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_on(self) -> bool:
        return self._state == "on"

    def snapshot(self) -> Session:
        return {"session_id": self._id, "state": self._state, "since": self._since, "by": self._by}

    def start(self, by: str = "card") -> Session:
        if by not in START_BY:
            raise ValueError(f"by must be one of {START_BY}")
        with self._lock:
            if self._state != "on":  # Start while on keeps the same session (double tap on the card)
                self._n += 1
                self._id = f"s{self._n}"
                self._state, self._since, self._by = "on", now_ms(), by
            self._last_activity = self._clock()
            return self.snapshot()

    def stop(self, by: str = "card") -> Session:
        if by not in STOP_REASONS:
            raise ValueError(f"by must be one of {STOP_REASONS}")
        with self._lock:
            if self._state != "off":
                self._state, self._since, self._by = "off", now_ms(), by
            return self.snapshot()

    def touch(self) -> None:
        """A segment was seen: push the idle stop back."""
        self._last_activity = self._clock()

    def idle_expired(self) -> bool:
        return self.is_on and self.idle_stop_s > 0 and self._clock() - self._last_activity >= self.idle_stop_s
