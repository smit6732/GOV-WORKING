import json
import datetime
from typing import Optional

from sqlalchemy.orm import Session
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from . import models
from .config import settings

# Gujarat bounding box (with small buffer around observed seed-data extents)
GUJARAT_LAT_RANGE = (19.5, 24.9)
GUJARAT_LON_RANGE = (68.0, 74.6)


def make_point(lat: float, lon: float):
    return from_shape(Point(lon, lat), srid=4326)


def in_gujarat_bbox(lat: float, lon: float) -> bool:
    return (
        GUJARAT_LAT_RANGE[0] <= lat <= GUJARAT_LAT_RANGE[1]
        and GUJARAT_LON_RANGE[0] <= lon <= GUJARAT_LON_RANGE[1]
    )


def camera_age_years(install_year: Optional[int]) -> Optional[int]:
    if not install_year:
        return None
    return datetime.datetime.utcnow().year - install_year


def camera_is_ageing(install_year: Optional[int]) -> bool:
    age = camera_age_years(install_year)
    if age is None:
        return False
    return age >= settings.expected_service_life_years


def write_audit_log(
    db: Session,
    user: Optional[models.User],
    action: str,
    entity_type: str,
    entity_id: Optional[str],
    details: Optional[dict] = None,
):
    log = models.AuditLog(
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=json.dumps(details) if details else None,
    )
    db.add(log)
    db.commit()
