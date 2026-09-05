from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..auth import require_roles, can_edit_camera
from ..utils import normalize_plate, user_department_scope, write_audit_log

router = APIRouter(tags=["tags-alerts"])


@router.get("/tags", response_model=list[schemas.TaggedPlateOut])
def list_tags(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "department_admin")),
):
    query = db.query(models.TaggedPlate).filter(models.TaggedPlate.is_active.is_(True))
    scope = user_department_scope(user)
    if scope is not None:
        query = query.filter(
            (models.TaggedPlate.department.is_(None)) | (models.TaggedPlate.department == scope)
        )
    return query.order_by(models.TaggedPlate.created_at.desc()).all()


@router.post("/tags", response_model=schemas.TaggedPlateOut, status_code=201)
def create_tag(
    payload: schemas.TaggedPlateCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "department_admin")),
):
    if not can_edit_camera(user, payload.department):
        raise HTTPException(403, "You may only tag plates for your own department (or leave it global, super_admin only)")
    if payload.department is None and user.role != models.UserRole.super_admin:
        raise HTTPException(403, "Only super_admin may create a global (all-department) tag")

    tag = models.TaggedPlate(
        plate_no=normalize_plate(payload.plate_no),
        reason=payload.reason,
        department=payload.department,
        tagged_by=user.email,
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)
    write_audit_log(db, user, "create", "tagged_plate", str(tag.id), {"plate_no": tag.plate_no})
    return tag


@router.delete("/tags/{tag_id}", status_code=204)
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "department_admin")),
):
    import datetime

    tag = db.query(models.TaggedPlate).filter(models.TaggedPlate.id == tag_id).first()
    if not tag:
        raise HTTPException(404, "Tag not found")
    if not can_edit_camera(user, tag.department):
        raise HTTPException(403, "You may only remove tags in your own department")

    tag.is_active = False
    tag.removed_at = datetime.datetime.utcnow()
    db.commit()
    write_audit_log(db, user, "delete", "tagged_plate", str(tag.id), {"plate_no": tag.plate_no})
    return None


@router.get("/alerts", response_model=schemas.AnprAlertListResponse)
def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "department_admin", "viewer")),
):
    query = db.query(models.AnprAlert)
    scope = user_department_scope(user)
    if scope is not None:
        camera_ids = [
            c[0] for c in db.query(models.Camera.camera_id).filter(models.Camera.department == scope).all()
        ]
        query = query.filter(models.AnprAlert.camera_id.in_(camera_ids))

    total = query.count()
    rows = (
        query.order_by(models.AnprAlert.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = []
    for a in rows:
        cam = db.query(models.Camera).filter(models.Camera.camera_id == a.camera_id).first()
        items.append(
            schemas.AnprAlertOut(
                id=a.id,
                event_id=a.event_id,
                camera_id=a.camera_id,
                tagged_plate_id=a.tagged_plate_id,
                plate_no=a.plate_no,
                matched_reason=a.matched_reason,
                created_at=a.created_at,
                district=cam.district if cam else None,
                department=cam.department if cam else None,
            )
        )
    return schemas.AnprAlertListResponse(total=total, page=page, page_size=page_size, items=items)
