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
    async with httpx.AsyncClient(timeout=10.0) as client:
        for i, cam in enumerate(cameras):
            try:
                resp = await client.post(
                    f"{settings.anpr_service_url}/stream/start",
                    json={"camera_id": cam.camera_id, "source": cam.rtsp_url, "target_fps": 2.0},
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
