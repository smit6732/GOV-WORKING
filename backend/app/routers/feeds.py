from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..anpr_client import get_stream_status
from ..database import get_db
from ..auth import get_current_user
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

    active_streams = set(await get_stream_status())

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
            analytics_capabilities=c.analytics_capabilities,
            stream_status="active" if c.camera_id in active_streams else "inactive",
        )
        for c in cameras
    ]
