import csv
import os
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import Base, engine, SessionLocal
from .config import settings
from . import models
from .auth import hash_password
from .utils import make_point

logger = logging.getLogger("seed")

DEMO_USERS = [
    dict(
        email="superadmin@gujaratpolice.gov.in",
        password="SuperAdmin@123",
        full_name="State CCTV Registry Super Admin",
        role=models.UserRole.super_admin,
        department=None,
    ),
    dict(
        email="deptadmin@gujaratpolice.gov.in",
        password="DeptAdmin@123",
        full_name="Home Department Admin",
        role=models.UserRole.department_admin,
        department="Home Department - Police",
    ),
    dict(
        email="viewer@gujaratpolice.gov.in",
        password="Viewer@123",
        full_name="Registry Viewer",
        role=models.UserRole.viewer,
        department=None,
    ),
]


def ensure_postgis(db: Session):
    db.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    db.commit()


def create_tables():
    Base.metadata.create_all(bind=engine)


def seed_users(db: Session):
    if db.query(models.User).count() > 0:
        return
    for u in DEMO_USERS:
        user = models.User(
            email=u["email"],
            hashed_password=hash_password(u["password"]),
            full_name=u["full_name"],
            role=u["role"],
            department=u["department"],
        )
        db.add(user)
    db.commit()
    logger.info("Seeded %d demo users", len(DEMO_USERS))


def _csv_path(filename: str) -> str:
    return os.path.join(settings.data_dir, filename)


def seed_stations(db: Session):
    if db.query(models.PoliceStation).count() > 0:
        return
    path = _csv_path(settings.stations_csv)
    if not os.path.exists(path):
        logger.warning("Stations CSV not found at %s, skipping", path)
        return
    count = 0
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except (ValueError, KeyError):
                continue
            station = models.PoliceStation(
                s_no=int(row["s_no"]) if row.get("s_no") else None,
                district=row["district"].strip(),
                station_name=row["station_name"].strip(),
                address=row.get("address", "").strip(),
                latitude=lat,
                longitude=lon,
                geom=make_point(lat, lon),
            )
            db.add(station)
            count += 1
            if count % 200 == 0:
                db.commit()
    db.commit()
    logger.info("Seeded %d police stations", count)


def seed_cameras(db: Session):
    if db.query(models.Camera).count() > 0:
        return
    path = _csv_path(settings.cameras_csv)
    if not os.path.exists(path):
        logger.warning("Cameras CSV not found at %s, skipping", path)
        return
    count = 0
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except (ValueError, KeyError):
                continue
            is_synth = str(row.get("is_synthetic", "TRUE")).strip().upper() in (
                "TRUE",
                "1",
                "YES",
            )
            retention = row.get("retention_days")
            install_year = row.get("install_year")
            camera = models.Camera(
                camera_id=row["camera_id"].strip(),
                district=row["district"].strip(),
                department=row["department"].strip(),
                nearest_station=row.get("nearest_station", "").strip(),
                camera_type=row["camera_type"].strip(),
                vendor=row.get("vendor", "").strip(),
                ownership=row.get("ownership", "Government").strip() or "Government",
                latitude=lat,
                longitude=lon,
                geom=make_point(lat, lon),
                storage_type=row.get("storage_type", "").strip(),
                retention_days=int(retention) if retention else None,
                install_year=int(install_year) if install_year else None,
                connectivity_status=row.get("connectivity_status", "Active").strip(),
                is_synthetic=is_synth,
                created_by="seed-script",
            )
            db.add(camera)
            count += 1
            if count % 200 == 0:
                db.commit()
    db.commit()
    logger.info("Seeded %d cameras", count)


# Model 2 demo cameras — carry rtsp_url/analytics_capabilities so the unified
# viewer + ANPR pipeline have at least 2 real feeds to work against. One per
# department so RBAC (department_admin scoping) is genuinely exercised.
MODEL2_DEMO_CAMERAS = [
    dict(
        camera_id="CAM-M2-001",
        district="Ahmedabad",
        department="Home Department - Police",
        nearest_station="Ahmedabad City Control Room",
        camera_type="IP Bullet",
        vendor="Hikvision",
        ownership="Government",
        latitude=23.0225,
        longitude=72.5714,
        storage_type="Cloud",
        retention_days=30,
        install_year=2023,
        connectivity_status="Active",
        rtsp_url="rtsp://mediamtx:8554/department_a",
        analytics_capabilities="anpr",
    ),
    dict(
        camera_id="CAM-M2-002",
        district="Surat",
        department="ACB",
        nearest_station="Surat ACB Office",
        camera_type="IP Dome",
        vendor="Bosch",
        ownership="Government",
        latitude=21.1702,
        longitude=72.8311,
        storage_type="Local NVR",
        retention_days=30,
        install_year=2023,
        connectivity_status="Active",
        rtsp_url="rtsp://mediamtx:8554/department_b",
        analytics_capabilities="anpr",
    ),
]


def seed_model2_cameras(db: Session):
    """Idempotent per-camera insert (not a blanket 'skip if table non-empty')
    so this safely adds the 2 demo feed cameras even on a database that
    already has the full CSV-seeded registry."""
    for c in MODEL2_DEMO_CAMERAS:
        if db.query(models.Camera).filter(models.Camera.camera_id == c["camera_id"]).first():
            continue
        camera = models.Camera(
            camera_id=c["camera_id"],
            district=c["district"],
            department=c["department"],
            nearest_station=c["nearest_station"],
            camera_type=c["camera_type"],
            vendor=c["vendor"],
            ownership=c["ownership"],
            latitude=c["latitude"],
            longitude=c["longitude"],
            geom=make_point(c["latitude"], c["longitude"]),
            storage_type=c["storage_type"],
            retention_days=c["retention_days"],
            install_year=c["install_year"],
            connectivity_status=c["connectivity_status"],
            rtsp_url=c["rtsp_url"],
            analytics_capabilities=c["analytics_capabilities"],
            is_synthetic=True,
            created_by="seed-script",
        )
        db.add(camera)
    db.commit()
    logger.info("Seeded Model 2 demo feed cameras (idempotent)")


def run_seed():
    db = SessionLocal()
    try:
        ensure_postgis(db)
    finally:
        db.close()

    create_tables()

    db = SessionLocal()
    try:
        seed_users(db)
        seed_stations(db)
        seed_cameras(db)
        seed_model2_cameras(db)
    finally:
        db.close()
