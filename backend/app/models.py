import enum
import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Text,
    Float,
)
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry

from .database import Base


class UserRole(str, enum.Enum):
    super_admin = "super_admin"
    department_admin = "department_admin"
    viewer = "viewer"


class ConnectivityStatus(str, enum.Enum):
    active = "Active"
    offline = "Offline"
    maintenance = "Maintenance"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(Enum(UserRole, name="user_role"), nullable=False, default=UserRole.viewer)
    # Department scoping for department_admin role; null = all departments (super_admin/viewer)
    department = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class PoliceStation(Base):
    __tablename__ = "police_stations"

    id = Column(Integer, primary_key=True, index=True)
    s_no = Column(Integer, nullable=True)
    district = Column(String(255), index=True, nullable=False)
    station_name = Column(String(255), nullable=False)
    address = Column(Text, nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    geom = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String(64), unique=True, index=True, nullable=False)
    district = Column(String(255), index=True, nullable=False)
    department = Column(String(255), index=True, nullable=False)
    nearest_station = Column(String(255), nullable=True)
    camera_type = Column(String(64), index=True, nullable=False)
    vendor = Column(String(128), nullable=True)
    ownership = Column(String(64), nullable=False, default="Government")
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    geom = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    storage_type = Column(String(64), nullable=True)
    retention_days = Column(Integer, nullable=True)
    install_year = Column(Integer, nullable=True)
    # Stored as a plain string (not a native Postgres/SQLAlchemy Enum) because
    # SQLAlchemy's Enum type persists the Python enum member's *name* by default,
    # which would mismatch ConnectivityStatus's name/value pairs (e.g. name
    # "active" vs value "Active"). Valid values are enforced at the Pydantic
    # schema layer via the ConnectivityStatus enum.
    connectivity_status = Column(String(32), nullable=False, default="Active")
    is_synthetic = Column(Boolean, default=False, nullable=False)

    # --- Model 2 additive fields (nullable; absent for the vast majority of the
    # registry, which has no live feed). analytics_capabilities is a plain
    # comma-separated string (e.g. "anpr"), matching the connectivity_status
    # convention of not using a native Postgres enum for simple tag-like values.
    rtsp_url = Column(String(512), nullable=True)
    onvif_url = Column(String(512), nullable=True)
    analytics_capabilities = Column(String(128), nullable=True)

    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_email = Column(String(255), nullable=True)
    action = Column(String(64), nullable=False)  # create | update | delete | bulk_upload | login
    entity_type = Column(String(64), nullable=False)  # camera | user | ...
    entity_id = Column(String(64), nullable=True)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    user = relationship("User")


# ==================== Model 2 — ANPR event pipeline ====================
# These tables are additive to the registry: they never duplicate camera
# metadata (camera_id is always a lookup key back into Camera), and nothing
# here changes any Model 1 behaviour.


class AnprEvent(Base):
    """Mirrors ANPR_Standalone's event schema (vehicle_detection /
    plate_only_detection), one row per Kafka message consumed. bbox fields are
    stored as JSON-in-Text, matching the existing AuditLog.details convention
    for structured-but-rarely-queried data."""

    __tablename__ = "anpr_events"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String(64), ForeignKey("cameras.camera_id"), index=True, nullable=False)
    event_type = Column(String(32), nullable=False)  # vehicle_detection | plate_only_detection
    timestamp = Column(DateTime, index=True, nullable=False)
    track_id = Column(Integer, nullable=True)
    vehicle_class = Column(String(32), nullable=True)
    vehicle_bbox = Column(Text, nullable=True)  # JSON [x1,y1,x2,y2]
    vehicle_confidence = Column(Float, nullable=True)
    plate_no = Column(String(32), index=True, nullable=True)
    plate_confidence = Column(Float, nullable=True)
    plate_bbox = Column(Text, nullable=True)  # JSON [x1,y1,x2,y2]
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class TaggedPlate(Base):
    """An operator-tagged plate of interest. Mirrors the registry's own
    department-scoping convention: department=None means every department's
    detections are checked against it (super_admin-created global tags)."""

    __tablename__ = "tagged_plates"

    id = Column(Integer, primary_key=True, index=True)
    plate_no = Column(String(32), index=True, nullable=False)
    reason = Column(String(255), nullable=True)
    department = Column(String(255), nullable=True)
    tagged_by = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    removed_at = Column(DateTime, nullable=True)


class AnprAlert(Base):
    """Created when a live AnprEvent's plate matches an active TaggedPlate."""

    __tablename__ = "anpr_alerts"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("anpr_events.id"), nullable=False)
    camera_id = Column(String(64), ForeignKey("cameras.camera_id"), index=True, nullable=False)
    tagged_plate_id = Column(Integer, ForeignKey("tagged_plates.id"), nullable=False)
    plate_no = Column(String(32), index=True, nullable=False)
    matched_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
