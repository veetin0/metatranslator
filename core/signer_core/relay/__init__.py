"""Relay (M1.2): FastAPI app `signer_core.relay.app:app` with the consent-gated /ws/frames, /ws/events fan-out,
session, feedback and reply endpoints, and the Signer Card at /. Run: `python -m signer_core.relay [--webcam]`.

Importing this package stays light; `from signer_core.relay.app import app, create_app` loads FastAPI.
"""
from .pipeline import JpegLandmarker, PhraseBuilder, Pipeline
from .session import SessionManager

__all__ = ["JpegLandmarker", "PhraseBuilder", "Pipeline", "SessionManager"]
