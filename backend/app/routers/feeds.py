from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from .. import models, schemas, anpr_client
from ..anpr_client import get_stream_health
from ..database import SessionLocal, get_db
from ..auth import get_current_user, require_roles
from ..utils import user_department_scope

router = APIRouter(prefix="/feeds", tags=["feeds"])


def _stream_path(rtsp_url: str) -> str:
    return urlparse(rtsp_url).path.lstrip("/")


@router.get("", response_model=list[schemas.FeedOut])
async def list_feeds(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Cameras Model 1 flags as ANPR-eligible (analytics_capabilities contains
    "anpr") with a stored rtsp_url — read straight off the registry's own
    Camera table, no duplicate camera data anywhere in Model 2."""
    query = (
        db.query(models.Camera)
        .filter(models.Camera.rtsp_url.isnot(None))
        .filter(models.Camera.analytics_capabilities.isnot(None))
        .filter(models.Camera.analytics_capabilities.ilike("%anpr%"))
    )
    scope = user_department_scope(user)
    if scope is not None:
        query = query.filter(models.Camera.department == scope)
    cameras = query.order_by(models.Camera.camera_id).all()

    # Real per-camera connectivity, not just "a background thread exists"
    # -- a stream stuck retrying an unreachable source is still tracked by
    # ANPR_Standalone, but isn't actually receiving frames.
    health = await get_stream_health()

    def _status(camera_id: str) -> str:
        entry = health.get(camera_id)
        if entry is None:
            return "inactive"  # no tracking thread assigned at all
        return "connected" if entry.get("connected") else "connecting"

    return [
        schemas.FeedOut(
            camera_id=c.camera_id,
            district=c.district,
            department=c.department,
            nearest_station=c.nearest_station,
            latitude=c.latitude,
            longitude=c.longitude,
            rtsp_url=c.rtsp_url,
            stream_path=_stream_path(c.rtsp_url),
            hls_url=c.hls_url,
            analytics_capabilities=c.analytics_capabilities,
            stream_status=_status(c.camera_id),
        )
        for c in cameras
    ]


# ---------------- Live Grid / Demo Mode switch ----------------
#
# The Video Wall's background camera tracking (up to 30+ real cameras) and
# the one-shot Live Demo Panel (webcam capture / photo upload) share ONE
# CPU-only ANPR_Standalone process. Running a full real grid can starve
# the one-shot panel badly enough to time out (confirmed directly: 30+
# active streams -> a plain /detect/image call exceeding 20s). Rather than
# hide that tradeoff, expose it: "Live Grid" mode runs background tracking
# on every analytics-capable camera; "Demo Mode" stops all of it so the
# webcam/upload panel gets full CPU. Never both at once.

@router.get("/live-grid/status")
async def live_grid_status(user: models.User = Depends(get_current_user)):
    active = await anpr_client.get_stream_status()
    return {"running": len(active) > 0, "active_camera_count": len(active)}


async def _start_all_streams_with_own_session():
    """Runs as a background task, after the triggering HTTP request has
    already returned -- the request-scoped `db` session from Depends(get_db)
    is closed by then, so this opens its own rather than reusing it."""
    db = SessionLocal()
    try:
        await anpr_client.start_all_streams(db)
    finally:
        db.close()


@router.post("/live-grid/start")
async def live_grid_start(
    background_tasks: BackgroundTasks,
    user: models.User = Depends(require_roles("super_admin", "department_admin")),
):
    # Starting a full grid is staggered (~1.5s/camera -- 30+ cameras is
    # 45s+) -- run it in the background and return immediately rather
    # than making the caller (and any client-side timeout) wait through
    # the whole thing. Poll GET /feeds/live-grid/status to see progress.
    background_tasks.add_task(_start_all_streams_with_own_session)
    return {"status": "starting"}


@router.post("/live-grid/stop")
async def live_grid_stop(user: models.User = Depends(require_roles("super_admin", "department_admin"))):
    result = await anpr_client.stop_all_streams()
    return {"status": "stopped", "detail": result}
