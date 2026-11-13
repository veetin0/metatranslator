"""Frozen shared types for Signer (see .hackforge/CONTRACTS.md). Change only by a contract change."""
from __future__ import annotations

import os
from typing import Literal, TypedDict

VERSION = "0.1.0"

# Landmark clip layout (CONTRACTS.md §5): 75 points, float16 (T, 75, 3)
POSE = range(0, 33)
LEFT_HAND = range(33, 54)
RIGHT_HAND = range(54, 75)
N_POINTS = 75
LAYOUT = {"pose": POSE, "left_hand": LEFT_HAND, "right_hand": RIGHT_HAND}
CLIP_KEYS = ("xyz", "t_ms", "fps", "gloss", "signer", "source")
REST = "REST"
RESAMPLE_STEPS = 32

Source = Literal["own", "popsign", "glasses", "webcam"]
Tier = Literal["confirmed", "unsure", "none"]
SessionState = Literal["off", "on", "paused"]
LensState = Literal["off", "connecting", "on", "paused", "glasses_off", "permission_denied", "core_down"]
Verdict = Literal["right", "wrong", "veto"]

CONF_HIGH = float(os.environ.get("SIGNER_CONF_HIGH", "0.80"))
CONF_LOW = float(os.environ.get("SIGNER_CONF_LOW", "0.50"))
IDLE_STOP_S = int(os.environ.get("SIGNER_IDLE_STOP_S", "120"))
NONE_TEXT = "Didn't catch that"


def tier_for(confidence: float, high: float = CONF_HIGH, low: float = CONF_LOW) -> Tier:
    if confidence >= high:
        return "confirmed"
    if confidence >= low:
        return "unsure"
    return "none"


class FrameHeader(TypedDict):
    seq: int
    ts_ms: int
    w: int
    h: int
    source: Literal["glasses", "webcam", "mock"]
    rot: int


class Session(TypedDict):
    session_id: str | None
    state: SessionState
    since: int
    by: str


class Alternative(TypedDict):
    text: str
    gloss: list[str]
    confidence: float


class CaptionEvent(TypedDict):
    type: Literal["caption"]
    id: str
    text: str
    gloss: list[str]
    tier: Tier
    confidence: float
    alternatives: list[Alternative]
    question: bool
    mode: Literal["template", "llm"]
    speak: bool
    ts: int


class StateEvent(TypedDict):
    type: Literal["state"]
    state: LensState
    link: Literal["ok", "slow"]
    ts: int


class ReplyEvent(TypedDict):
    type: Literal["reply"]
    text: str
    source: Literal["stt", "typed"]
    ts: int


class StatsEvent(TypedDict):
    type: Literal["stats"]
    confirmed: int
    total: int


def pack_frame(header: FrameHeader, jpeg: bytes) -> bytes:
    import json
    import struct

    h = json.dumps(header, separators=(",", ":")).encode()
    return struct.pack(">I", len(h)) + h + jpeg


def unpack_frame(msg: bytes) -> tuple[FrameHeader, bytes]:
    import json
    import struct

    (n,) = struct.unpack(">I", msg[:4])
    return json.loads(msg[4 : 4 + n]), msg[4 + n :]
