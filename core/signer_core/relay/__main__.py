"""python -m signer_core.relay [--webcam [--camera N]]

Serves the relay on SIGNER_HOST:SIGNER_PORT. `--webcam` also feeds this laptop's camera in-process (CONTRACTS §1
dev source): frames are only read while the session is `on`, go straight to the pipeline and are dropped.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import threading
import time


def webcam_loop(app, loop: asyncio.AbstractEventLoop, camera: int, stop: threading.Event) -> None:
    from ..sources.webcam import CameraError, WebcamSource
    from .pipeline import JpegLandmarker

    relay = app.state.relay
    marker = JpegLandmarker()
    log = logging.getLogger("signer.webcam")
    while not stop.is_set():
        if not relay.session.is_on:
            time.sleep(0.2)
            continue
        try:
            with WebcamSource(camera) as src:
                log.info("webcam %d open", camera)
                for frame, ts in src:
                    if stop.is_set() or not relay.session.is_on:
                        break
                    events = relay.pipeline.push_landmarks(marker.landmarks(frame, ts), ts)
                    if events:
                        asyncio.run_coroutine_threadsafe(relay.emit(events), loop)
        except CameraError as e:
            log.error("%s", e)
            time.sleep(2.0)
    marker.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Signer relay (FastAPI).")
    ap.add_argument("--host", default=os.environ.get("SIGNER_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("SIGNER_PORT", "8000")))
    ap.add_argument("--webcam", action="store_true", help="feed this laptop's camera in-process while the session is on")
    ap.add_argument("--camera", type=int, default=0)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    import uvicorn

    from .app import app

    config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
    server = uvicorn.Server(config)

    async def serve():
        stop = threading.Event()
        if args.webcam:
            loop = asyncio.get_running_loop()
            threading.Thread(target=webcam_loop, args=(app, loop, args.camera, stop), daemon=True).start()
        try:
            await server.serve()
        finally:
            stop.set()

    asyncio.run(serve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
