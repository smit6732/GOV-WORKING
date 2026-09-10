"""Thin client for ANPR_Standalone's own HTTP API — orchestration only
(start/stop tracking on real registry cameras). The browser's Live Demo
Panel calls ANPR_Standalone's /detect/image directly on its exposed port;
this module is purely server-side "run /stream/start against each
analytics-capable camera" wiring."""

import asyncio
import logging

import httpx
from sqlalchemy.orm import Session

from . import models
from .config import settings

logger = logging.getLogger("anpr_client")

# Delay between successive /stream/start calls when bringing up many cameras
# at once (e.g. backend startup with a full 30-camera grid registered). Each
# call triggers ANPR_Standalone to open a real RTSP connection almost
# immediately in its background thread, so firing all of them in a tight
# loop opens dozens of concurrent connections against one real server at
# once -- exactly what the Sentinel Grid integration spec says not to do,
# and observed in practice to cause later cameras in the loop to fail to
# open at all while earlier ones succeed. A small stagger costs nothing for
# the common case of a couple of demo cameras and avoids hammering a real
# server when many are registered.
_STREAM_START_STAGGER_SECONDS = 1.5

# Per-camera inference rate for background stream tracking. This is CPU-only
# YOLOv8 + PaddleOCR inference sharing ONE process with every other camera
# AND the one-shot /detect/image demo endpoint. Directly reproduced the
# consequence of the old 2.0 value with a real 32-camera grid running (30
# Sentinel Grid cameras + 2 local demo feeds): up to 64 inference passes/sec
# demanded of one CPU-only process, which starved /detect/image so badly a
# plain request timed out after 30+ seconds -- from the browser, the "My
# Webcam"/"Upload Photo" Live Demo Panel just sat on "Detecting..." forever
# with no error (that fetch call has no timeout of its own either -- see
# VideoWall.jsx). A handful of cameras at 2.0 fps was never the problem;
# a full real-world grid was. Lower default so a full grid leaves the demo
# endpoint responsive; a small demo (1-2 cameras) barely notices the
# difference at either value.
_DEFAULT_TARGET_FPS = 0.5

# ANPR_Standalone loads YOLOv8 + PaddleOCR at import time, before its
# uvicorn server starts accepting requests -- this can take well over a
# minute. The backend has no docker-compose `depends_on` ordering against
# it (compose's own health-check-gated depends_on can't express "and the
# app inside has finished loading its models" anyway), so on a fresh
# `docker compose up` or a backend-only restart, start_all_streams() can
# run before ANPR_Standalone is reachable at all. Observed directly this
# session: "ANPR service unreachable" on every camera right after an anpr
# container restart. Previously this just logged a warning and gave up
# for that boot -- streams only started at all if someone noticed and
# restarted the backend again. Poll /health first instead.
_ANPR_READY_POLL_INTERVAL_SECONDS = 2.0
_ANPR_READY_MAX_WAIT_SECONDS = 90.0


async def _wait_for_anpr_ready() -> bool:
    """Poll ANPR_Standalone's /health until it responds, up to a bounded
    timeout. Returns True once ready, False if the timeout is hit (caller
    proceeds anyway -- the per-camera calls will just log their own
    per-camera warnings same as before, rather than blocking startup
    forever on a genuinely-down service)."""
    deadline = asyncio.get_event_loop().time() + _ANPR_READY_MAX_WAIT_SECONDS
    async with httpx.AsyncClient(timeout=3.0) as client:
        while True:
            try:
                resp = await client.get(f"{settings.anpr_service_url}/health")
                if resp.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass

            if asyncio.get_event_loop().time() >= deadline:
                logger.warning(
                    "ANPR service still not reachable after %.0fs -- proceeding "
                    "anyway, individual stream starts may fail",
                    _ANPR_READY_MAX_WAIT_SECONDS,
                )
                return False
            await asyncio.sleep(_ANPR_READY_POLL_INTERVAL_SECONDS)


def _analytics_capable_cameras(db: Session):
    return (
        db.query(models.Camera)
        .filter(models.Camera.rtsp_url.isnot(None))
        .filter(models.Camera.analytics_capabilities.isnot(None))
        .filter(models.Camera.analytics_capabilities.ilike("%anpr%"))
        .all()
    )


async def start_all_streams(db: Session):
    cameras = _analytics_capable_cameras(db)
    if not cameras:
        logger.info("No analytics-capable cameras found; nothing to start on ANPR_Standalone")
        return

    ready = await _wait_for_anpr_ready()
    if ready:
        logger.info("ANPR service is up -- starting streams for %d camera(s)", len(cameras))

    async with httpx.AsyncClient(timeout=10.0) as client:
        for i, cam in enumerate(cameras):
            try:
                resp = await client.post(
                    f"{settings.anpr_service_url}/stream/start",
                    json={"camera_id": cam.camera_id, "source": cam.rtsp_url, "target_fps": _DEFAULT_TARGET_FPS},
                )
                if resp.status_code == 409:
                    logger.info("ANPR stream already running for %s", cam.camera_id)
                elif resp.status_code >= 400:
                    logger.warning(
                        "Could not start ANPR stream for %s: %s %s",
                        cam.camera_id, resp.status_code, resp.text,
                    )
                else:
                    logger.info("Started ANPR stream for %s (%s)", cam.camera_id, cam.rtsp_url)
            except httpx.HTTPError as e:
                logger.warning("ANPR service unreachable while starting %s: %s", cam.camera_id, e)

            if i < len(cameras) - 1:
                await asyncio.sleep(_STREAM_START_STAGGER_SECONDS)


async def stop_all_streams() -> dict:
    """Stop every currently-tracked stream at once, via ANPR_Standalone's
    bulk /stream/stop_all. Used by the Video Wall's live-grid/demo-mode
    switch -- the one-shot /detect/image endpoint (webcam capture, photo
    upload) shares this same CPU-only process with every background
    camera, so a real camera grid running can starve it badly enough to
    time out (confirmed directly: 30+ real streams -> a plain detect
    call exceeding 20s). Freeing the background load entirely, rather
    than just throttling it, is the only way to guarantee the one-shot
    panel gets full CPU."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{settings.anpr_service_url}/stream/stop_all")
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        logger.warning("Failed to stop all ANPR streams: %s", e)
        return {"status": "error", "detail": str(e)}


async def get_stream_status() -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.anpr_service_url}/stream/status")
            resp.raise_for_status()
            return resp.json().get("active_streams", [])
    except httpx.HTTPError:
        return []


async def get_stream_health() -> dict:
    """Real per-camera connectivity (is video actually flowing right now),
    not just 'a background thread is assigned and trying' -- a stream
    stuck in reconnect-backoff still shows up in get_stream_status()'s
    plain list, but connected=False here. Returns {} (treated as unknown)
    if the ANPR service itself is unreachable."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.anpr_service_url}/streams/health")
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError:
        return {}
