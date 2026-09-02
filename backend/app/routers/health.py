from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user
from ..config import settings
from ..utils import camera_age_years, camera_is_ageing

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/ageing", response_model=schemas.HealthSummary)
def ageing_report(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    cameras = db.query(models.Camera).all()

    items = []
    ageing_count = 0
    offline_count = 0
    maintenance_count = 0
    needs_attention = 0

    for c in cameras:
        flags = []
        is_ageing = camera_is_ageing(c.install_year)
        if is_ageing:
            flags.append("ageing")
            ageing_count += 1
        if c.connectivity_status == models.ConnectivityStatus.offline:
            flags.append("offline")
            offline_count += 1
        if c.connectivity_status == models.ConnectivityStatus.maintenance:
            flags.append("maintenance")
            maintenance_count += 1

        if flags:
            needs_attention += 1
            out = schemas.HealthCameraOut(
                **schemas.CameraOut.model_validate(c).model_dump(),
                flags=flags,
            )
            out.age_years = camera_age_years(c.install_year)
            out.is_ageing = is_ageing
            items.append(out)

    items.sort(key=lambda x: (x.age_years or 0), reverse=True)

    return schemas.HealthSummary(
        ageing_count=ageing_count,
        offline_count=offline_count,
        maintenance_count=maintenance_count,
        needs_attention_count=needs_attention,
        expected_service_life_years=settings.expected_service_life_years,
        items=items,
    )
