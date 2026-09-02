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
