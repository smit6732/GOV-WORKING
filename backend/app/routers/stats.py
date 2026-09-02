from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user
from ..utils import camera_is_ageing

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/dashboard", response_model=schemas.DashboardStats)
def dashboard_stats(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    cameras = db.query(models.Camera).all()

    total = len(cameras)
    online = sum(1 for c in cameras if c.connectivity_status == models.ConnectivityStatus.active)
    offline = sum(1 for c in cameras if c.connectivity_status == models.ConnectivityStatus.offline)
    maintenance = sum(1 for c in cameras if c.connectivity_status == models.ConnectivityStatus.maintenance)
    ageing = sum(1 for c in cameras if camera_is_ageing(c.install_year))
    synthetic = sum(1 for c in cameras if c.is_synthetic)

    by_department = Counter(c.department for c in cameras)
    by_camera_type = Counter(c.camera_type for c in cameras)
    by_district = Counter(c.district for c in cameras)
    by_ownership = Counter(c.ownership for c in cameras)
    by_storage_type = Counter(c.storage_type for c in cameras if c.storage_type)
    by_install_year = Counter(str(c.install_year) for c in cameras if c.install_year)

    return schemas.DashboardStats(
        total_cameras=total,
        online=online,
        offline=offline,
        maintenance=maintenance,
        ageing=ageing,
        synthetic=synthetic,
        by_department=dict(by_department),
        by_camera_type=dict(by_camera_type),
        by_district=dict(by_district.most_common(15)),
        by_ownership=dict(by_ownership),
        by_storage_type=dict(by_storage_type),
        by_install_year=dict(sorted(by_install_year.items())),
    )
