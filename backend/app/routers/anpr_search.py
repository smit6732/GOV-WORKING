import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user
from ..utils import normalize_plate, user_department_scope
from .. import es_client

router = APIRouter(tags=["anpr-search"])


def _camera_ids_in_scope(db: Session, department: Optional[str]) -> Optional[list[str]]:
    if department is None:
        return None
    return [
        c[0] for c in db.query(models.Camera.camera_id).filter(models.Camera.department == department).all()
    ]


def _enrich(db: Session, hit: dict) -> dict:
    cam = db.query(models.Camera).filter(models.Camera.camera_id == hit.get("camera_id")).first()
    hit = dict(hit)
    hit["district"] = cam.district if cam else None
    hit["department"] = cam.department if cam else None
    return hit


@router.get("/vehicles/search")
def search_vehicles(
    plate: Optional[str] = None,
    camera_id: Optional[str] = None,
    department: Optional[str] = None,
    track_id: Optional[int] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    scope = user_department_scope(user)
    if scope is not None and department and department != scope:
        raise HTTPException(403, "You may only search within your own department")
    effective_department = scope or department
    camera_ids_scope = _camera_ids_in_scope(db, effective_department)

    try:
        hits = es_client.search_events(
            plate_no=normalize_plate(plate) if plate else None,
            camera_id=camera_id,
            track_id=track_id,
            start_time=start_time,
            end_time=end_time,
            camera_ids_scope=camera_ids_scope,
        )
    except Exception as e:
        raise HTTPException(503, f"Search index unavailable: {e}")

    return {"total": len(hits), "items": [_enrich(db, h) for h in hits]}


@router.get("/vehicles/{plate_no}/history", response_model=list[schemas.VehicleHistoryPoint])
def vehicle_history(
    plate_no: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Chronological detections for one plate, Postgres-backed (the
    authoritative store) — drives the route/movement-history map view."""
    normalized = normalize_plate(plate_no)
    query = db.query(models.AnprEvent).filter(models.AnprEvent.plate_no == normalized)

    scope = user_department_scope(user)
    if scope is not None:
        camera_ids = _camera_ids_in_scope(db, scope) or []
        query = query.filter(models.AnprEvent.camera_id.in_(camera_ids))

    events = query.order_by(models.AnprEvent.timestamp.asc()).all()

    points = []
    for e in events:
        cam = db.query(models.Camera).filter(models.Camera.camera_id == e.camera_id).first()
        points.append(
            schemas.VehicleHistoryPoint(
                event_id=e.id,
                camera_id=e.camera_id,
                district=cam.district if cam else None,
                department=cam.department if cam else None,
                latitude=cam.latitude if cam else None,
                longitude=cam.longitude if cam else None,
                timestamp=e.timestamp,
                plate_no=e.plate_no,
                plate_confidence=e.plate_confidence,
                track_id=e.track_id,
            )
        )
    return points


@router.get("/anpr-events", response_model=schemas.AnprEventListResponse)
def list_anpr_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    camera_id: Optional[str] = None,
    department: Optional[str] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Postgres-backed listing — 'registry and analytics data queryable
    together': joins each event's camera back to district/department."""
    query = db.query(models.AnprEvent)
    if camera_id:
        query = query.filter(models.AnprEvent.camera_id == camera_id)

    scope = user_department_scope(user)
    effective_department = scope or department
    if effective_department:
        camera_ids = _camera_ids_in_scope(db, effective_department) or []
        query = query.filter(models.AnprEvent.camera_id.in_(camera_ids))

    total = query.count()
    rows = (
        query.order_by(models.AnprEvent.timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for e in rows:
        cam = db.query(models.Camera).filter(models.Camera.camera_id == e.camera_id).first()
        items.append(
            schemas.AnprEventOut(
                id=e.id,
                camera_id=e.camera_id,
                event_type=e.event_type,
                timestamp=e.timestamp,
                track_id=e.track_id,
                vehicle_class=e.vehicle_class,
                vehicle_bbox=json.loads(e.vehicle_bbox) if e.vehicle_bbox else None,
                vehicle_confidence=e.vehicle_confidence,
                plate_no=e.plate_no,
                plate_confidence=e.plate_confidence,
                plate_bbox=json.loads(e.plate_bbox) if e.plate_bbox else None,
                created_at=e.created_at,
                district=cam.district if cam else None,
                department=cam.department if cam else None,
            )
        )
    return schemas.AnprEventListResponse(total=total, page=page, page_size=page_size, items=items)
