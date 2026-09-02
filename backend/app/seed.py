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
    finally:
        db.close()
