import csv
import io
import re
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user, require_roles, can_edit_camera
from ..utils import make_point, camera_age_years, camera_is_ageing, write_audit_log, in_gujarat_bbox

router = APIRouter(prefix="/cameras", tags=["cameras"])

VALID_CAMERA_TYPES = set(schemas.CAMERA_TYPES)
VALID_DEPARTMENTS = set(schemas.DEPARTMENTS)
VALID_STORAGE_TYPES = set(schemas.STORAGE_TYPES)
VALID_OWNERSHIP = set(schemas.OWNERSHIP_TYPES)
VALID_CONNECTIVITY = {e.value for e in models.ConnectivityStatus}


def _to_out(cam: models.Camera) -> schemas.CameraOut:
    data = schemas.CameraOut.model_validate(cam)
    data.age_years = camera_age_years(cam.install_year)
    data.is_ageing = camera_is_ageing(cam.install_year)
    return data


def _apply_filters(query, department, camera_type, district, connectivity_status, is_synthetic, search):
    if department:
        query = query.filter(models.Camera.department == department)
    if camera_type:
        query = query.filter(models.Camera.camera_type == camera_type)
    if district:
        query = query.filter(models.Camera.district == district)
    if connectivity_status:
        query = query.filter(models.Camera.connectivity_status == connectivity_status)
    if is_synthetic is not None:
        query = query.filter(models.Camera.is_synthetic == is_synthetic)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                models.Camera.camera_id.ilike(like),
                models.Camera.nearest_station.ilike(like),
                models.Camera.district.ilike(like),
            )
        )
    return query


@router.get("", response_model=schemas.CameraListResponse)
def list_cameras(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=2000),
    department: Optional[str] = None,
    camera_type: Optional[str] = None,
    district: Optional[str] = None,
    connectivity_status: Optional[str] = None,
    is_synthetic: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    query = db.query(models.Camera)
    query = _apply_filters(query, department, camera_type, district, connectivity_status, is_synthetic, search)
    total = query.count()
    items = (
        query.order_by(models.Camera.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.CameraListResponse(
        total=total, page=page, page_size=page_size, items=[_to_out(c) for c in items]
    )


@router.get("/geojson")
def cameras_geojson(
    department: Optional[str] = None,
    camera_type: Optional[str] = None,
    district: Optional[str] = None,
    connectivity_status: Optional[str] = None,
    is_synthetic: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    query = db.query(models.Camera)
    query = _apply_filters(query, department, camera_type, district, connectivity_status, is_synthetic, search)
    cameras = query.all()
    features = []
    for c in cameras:
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [c.longitude, c.latitude]},
                "properties": {
                    "id": c.id,
                    "camera_id": c.camera_id,
                    "district": c.district,
                    "department": c.department,
                    "nearest_station": c.nearest_station,
                    "camera_type": c.camera_type,
                    "vendor": c.vendor,
                    "ownership": c.ownership,
                    "storage_type": c.storage_type,
                    "retention_days": c.retention_days,
                    "install_year": c.install_year,
                    "connectivity_status": c.connectivity_status.value
                    if hasattr(c.connectivity_status, "value")
                    else c.connectivity_status,
                    "is_synthetic": c.is_synthetic,
                    "age_years": camera_age_years(c.install_year),
                    "is_ageing": camera_is_ageing(c.install_year),
                    "rtsp_url": c.rtsp_url,
                    "onvif_url": c.onvif_url,
                    "analytics_capabilities": c.analytics_capabilities,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


@router.get("/export")
def export_cameras_csv(
    department: Optional[str] = None,
    camera_type: Optional[str] = None,
    district: Optional[str] = None,
    connectivity_status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    query = db.query(models.Camera)
    query = _apply_filters(query, department, camera_type, district, connectivity_status, None, None)
    cameras = query.order_by(models.Camera.id).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "camera_id", "district", "department", "nearest_station", "camera_type",
            "vendor", "ownership", "latitude", "longitude", "storage_type",
            "retention_days", "install_year", "connectivity_status", "is_synthetic",
            "age_years", "is_ageing",
        ]
    )
    for c in cameras:
        writer.writerow(
            [
                c.camera_id, c.district, c.department, c.nearest_station, c.camera_type,
                c.vendor, c.ownership, c.latitude, c.longitude, c.storage_type,
                c.retention_days, c.install_year,
                c.connectivity_status.value if hasattr(c.connectivity_status, "value") else c.connectivity_status,
                c.is_synthetic, camera_age_years(c.install_year), camera_is_ageing(c.install_year),
            ]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=camera_registry_export.csv"},
    )


@router.get("/meta/options")
def camera_field_options(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    districts = [r[0] for r in db.query(models.Camera.district).distinct().order_by(models.Camera.district).all()]
    return {
        "camera_types": schemas.CAMERA_TYPES,
        "vendors": schemas.VENDORS,
        "departments": schemas.DEPARTMENTS,
        "storage_types": schemas.STORAGE_TYPES,
        "ownership_types": schemas.OWNERSHIP_TYPES,
        "connectivity_statuses": sorted(VALID_CONNECTIVITY),
        "districts": districts,
    }


@router.get("/{camera_id}", response_model=schemas.CameraOut)
def get_camera(camera_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    cam = db.query(models.Camera).filter(models.Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(404, "Camera not found")
    return _to_out(cam)


def _next_camera_id(db: Session) -> str:
    last = (
        db.query(models.Camera.camera_id)
        .filter(models.Camera.camera_id.op("~")(r"^CAM\d+$"))
        .order_by(models.Camera.id.desc())
        .all()
    )
    max_n = 0
    for (cid,) in last:
        m = re.match(r"^CAM(\d+)$", cid)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"CAM{max_n + 1:05d}"


@router.post("", response_model=schemas.CameraOut, status_code=201)
def create_camera(
    payload: schemas.CameraCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "department_admin")),
):
    if not can_edit_camera(user, payload.department):
        raise HTTPException(403, "You may only add cameras for your own department")
    if not in_gujarat_bbox(payload.latitude, payload.longitude):
        raise HTTPException(400, "Coordinates fall outside the expected Gujarat bounding box")

    camera_id = payload.camera_id or _next_camera_id(db)
    if db.query(models.Camera).filter(models.Camera.camera_id == camera_id).first():
        raise HTTPException(400, f"camera_id {camera_id} already exists")

    cam = models.Camera(
        camera_id=camera_id,
        district=payload.district,
        department=payload.department,
        nearest_station=payload.nearest_station,
        camera_type=payload.camera_type,
        vendor=payload.vendor,
        ownership=payload.ownership,
        latitude=payload.latitude,
        longitude=payload.longitude,
        geom=make_point(payload.latitude, payload.longitude),
        storage_type=payload.storage_type,
        retention_days=payload.retention_days,
        install_year=payload.install_year,
        connectivity_status=payload.connectivity_status,
        rtsp_url=payload.rtsp_url,
        onvif_url=payload.onvif_url,
        analytics_capabilities=payload.analytics_capabilities,
        is_synthetic=False,
        created_by=user.email,
    )
    db.add(cam)
    db.commit()
    db.refresh(cam)
    write_audit_log(db, user, "create", "camera", cam.camera_id, {"payload": payload.model_dump(mode="json")})
    return _to_out(cam)


@router.put("/{camera_id}", response_model=schemas.CameraOut)
def update_camera(
    camera_id: int,
    payload: schemas.CameraUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "department_admin")),
):
    cam = db.query(models.Camera).filter(models.Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(404, "Camera not found")
    if not can_edit_camera(user, cam.department):
        raise HTTPException(403, "You may only edit cameras in your own department")

    update_data = payload.model_dump(exclude_unset=True)
    new_dept = update_data.get("department", cam.department)
    if not can_edit_camera(user, new_dept):
        raise HTTPException(403, "You may not move a camera to another department")

    lat = update_data.get("latitude", cam.latitude)
    lon = update_data.get("longitude", cam.longitude)
    if ("latitude" in update_data or "longitude" in update_data) and not in_gujarat_bbox(lat, lon):
        raise HTTPException(400, "Coordinates fall outside the expected Gujarat bounding box")

    for field, value in update_data.items():
        setattr(cam, field, value)
    if "latitude" in update_data or "longitude" in update_data:
        cam.geom = make_point(lat, lon)

    db.commit()
    db.refresh(cam)
    write_audit_log(db, user, "update", "camera", cam.camera_id, {"changed": update_data})
    return _to_out(cam)


@router.delete("/{camera_id}", status_code=204)
def delete_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "department_admin")),
):
    cam = db.query(models.Camera).filter(models.Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(404, "Camera not found")
    if not can_edit_camera(user, cam.department):
        raise HTTPException(403, "You may only delete cameras in your own department")

    cid = cam.camera_id
    db.delete(cam)
    db.commit()
    write_audit_log(db, user, "delete", "camera", cid, None)
    return None


# ---------- Bulk upload ----------

REQUIRED_COLUMNS = [
    "camera_id", "district", "department", "nearest_station", "camera_type",
    "vendor", "ownership", "latitude", "longitude", "storage_type",
    "retention_days", "install_year", "connectivity_status",
]


def _validate_row(row: dict, row_number: int, existing_ids: set, seen_ids: set) -> tuple:
    errors = []

    camera_id = (row.get("camera_id") or "").strip()
    if camera_id:
        if camera_id in existing_ids:
            errors.append(f"camera_id '{camera_id}' already exists in the database")
        if camera_id in seen_ids:
            errors.append(f"camera_id '{camera_id}' duplicated within the uploaded file")

    district = (row.get("district") or "").strip()
    if not district:
        errors.append("district is required")

    department = (row.get("department") or "").strip()
    if department not in VALID_DEPARTMENTS:
        errors.append(f"department must be one of {sorted(VALID_DEPARTMENTS)}")

    camera_type = (row.get("camera_type") or "").strip()
    if camera_type not in VALID_CAMERA_TYPES:
        errors.append(f"camera_type must be one of {sorted(VALID_CAMERA_TYPES)}")

    ownership = (row.get("ownership") or "Government").strip() or "Government"

    storage_type = (row.get("storage_type") or "").strip()

    try:
        lat = float(row.get("latitude"))
        lon = float(row.get("longitude"))
        if not in_gujarat_bbox(lat, lon):
            errors.append("latitude/longitude fall outside the expected Gujarat bounding box")
    except (TypeError, ValueError):
        lat = lon = None
        errors.append("latitude and longitude must be numeric")

    retention_days = row.get("retention_days")
    try:
        retention_days = int(retention_days) if retention_days not in (None, "") else None
    except ValueError:
        errors.append("retention_days must be an integer")
        retention_days = None

    install_year = row.get("install_year")
    try:
        install_year = int(install_year) if install_year not in (None, "") else None
        if install_year and not (2000 <= install_year <= 2100):
            errors.append("install_year looks invalid")
    except ValueError:
        errors.append("install_year must be an integer")
        install_year = None

    connectivity_status = (row.get("connectivity_status") or "Active").strip() or "Active"
    if connectivity_status not in VALID_CONNECTIVITY:
        errors.append(f"connectivity_status must be one of {sorted(VALID_CONNECTIVITY)}")

    parsed = None
    if not errors:
        parsed = schemas.CameraCreate(
            camera_id=camera_id or None,
            district=district,
            department=department,
            nearest_station=(row.get("nearest_station") or "").strip() or None,
            camera_type=camera_type,
            vendor=(row.get("vendor") or "").strip() or None,
            ownership=ownership,
            latitude=lat,
            longitude=lon,
            storage_type=storage_type or None,
            retention_days=retention_days,
            install_year=install_year,
            connectivity_status=connectivity_status,
        )
    return parsed, errors


@router.post("/bulk-upload/preview", response_model=schemas.BulkUploadPreviewResponse)
async def bulk_upload_preview(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "department_admin")),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Only .csv files are supported")

    raw = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing_cols:
        raise HTTPException(400, f"CSV is missing required columns: {missing_cols}")

    existing_ids = {r[0] for r in db.query(models.Camera.camera_id).all()}
    seen_ids = set()

    valid_rows: List[schemas.CameraCreate] = []
    errors: List[schemas.BulkUploadRowError] = []
    total = 0
    dup_count = 0

    for i, row in enumerate(reader, start=2):  # row 1 is header
        total += 1
        parsed, row_errors = _validate_row(row, i, existing_ids, seen_ids)
        camera_id = (row.get("camera_id") or "").strip()
        if camera_id:
            if camera_id in existing_ids:
                dup_count += 1
            seen_ids.add(camera_id)
        if row_errors:
            errors.append(schemas.BulkUploadRowError(row_number=i, errors=row_errors, raw=row))
        else:
            valid_rows.append(parsed)

    if user.role == models.UserRole.department_admin:
        blocked = [r for r in valid_rows if r.department != user.department]
        valid_rows = [r for r in valid_rows if r.department == user.department]
        for b in blocked:
            errors.append(
                schemas.BulkUploadRowError(
                    row_number=0, errors=[f"Row department '{b.department}' outside your scope"], raw=b.model_dump(mode="json")
                )
            )

    return schemas.BulkUploadPreviewResponse(
        total_rows=total,
        valid_count=len(valid_rows),
        invalid_count=len(errors),
        duplicate_camera_ids_in_db=dup_count,
        preview_valid_rows=valid_rows[:50],
        all_valid_rows=valid_rows,
        errors=errors[:200],
    )


@router.post("/bulk-upload/commit", response_model=schemas.BulkUploadCommitResponse)
def bulk_upload_commit(
    payload: schemas.BulkUploadCommitRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("super_admin", "department_admin")),
):
    existing_ids = {r[0] for r in db.query(models.Camera.camera_id).all()}
    inserted = 0
    skipped = 0

    for row in payload.rows:
        if not can_edit_camera(user, row.department):
            skipped += 1
            continue
        camera_id = row.camera_id or _next_camera_id(db)
        if camera_id in existing_ids:
            skipped += 1
            continue
        if not in_gujarat_bbox(row.latitude, row.longitude):
            skipped += 1
            continue
        cam = models.Camera(
            camera_id=camera_id,
            district=row.district,
            department=row.department,
            nearest_station=row.nearest_station,
            camera_type=row.camera_type,
            vendor=row.vendor,
            ownership=row.ownership,
            latitude=row.latitude,
            longitude=row.longitude,
            geom=make_point(row.latitude, row.longitude),
            storage_type=row.storage_type,
            retention_days=row.retention_days,
            install_year=row.install_year,
            connectivity_status=row.connectivity_status,
            is_synthetic=False,
            created_by=user.email,
        )
        db.add(cam)
        existing_ids.add(camera_id)
        inserted += 1

    db.commit()
    write_audit_log(
        db, user, "bulk_upload", "camera", None,
        {"inserted": inserted, "skipped_duplicates": skipped},
    )
    return schemas.BulkUploadCommitResponse(inserted=inserted, skipped_duplicates=skipped)
