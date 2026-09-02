import datetime
from typing import Optional, List, Any

from pydantic import BaseModel, EmailStr, Field, ConfigDict

from .models import UserRole, ConnectivityStatus


# ---------- Auth / Users ----------

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    department: Optional[str] = None
    is_active: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str
    role: UserRole = UserRole.viewer
    department: Optional[str] = None


# ---------- Camera ----------

CAMERA_TYPES = ["IP Bullet", "IP Dome", "IP PTZ", "Analog Dome", "Analog PTZ"]
VENDORS = ["Bosch", "Hikvision", "Dahua", "Honeywell", "CP Plus"]
DEPARTMENTS = ["Home Department - Police", "ACB", "CID Crime"]
STORAGE_TYPES = ["Local NVR", "Cloud", "DVR"]
OWNERSHIP_TYPES = ["Government", "Private", "PPP"]


class CameraBase(BaseModel):
    district: str
    department: str
    nearest_station: Optional[str] = None
    camera_type: str
    vendor: Optional[str] = None
    ownership: str = "Government"
    latitude: float
    longitude: float
    storage_type: Optional[str] = None
    retention_days: Optional[int] = None
    install_year: Optional[int] = None
    connectivity_status: ConnectivityStatus = ConnectivityStatus.active


class CameraCreate(CameraBase):
    camera_id: Optional[str] = None  # auto-generated if omitted


class CameraUpdate(BaseModel):
    district: Optional[str] = None
    department: Optional[str] = None
    nearest_station: Optional[str] = None
    camera_type: Optional[str] = None
    vendor: Optional[str] = None
    ownership: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    storage_type: Optional[str] = None
    retention_days: Optional[int] = None
    install_year: Optional[int] = None
    connectivity_status: Optional[ConnectivityStatus] = None


class CameraOut(CameraBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    camera_id: str
    is_synthetic: bool
    created_by: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    age_years: Optional[int] = None
    is_ageing: Optional[bool] = None


class CameraListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[CameraOut]


# ---------- Bulk upload ----------

class BulkUploadRowError(BaseModel):
    row_number: int
    errors: List[str]
    raw: dict


class BulkUploadPreviewResponse(BaseModel):
    total_rows: int
    valid_count: int
    invalid_count: int
    duplicate_camera_ids_in_db: int
    preview_valid_rows: List[CameraCreate]
    all_valid_rows: List[CameraCreate]
    errors: List[BulkUploadRowError]


class BulkUploadCommitRequest(BaseModel):
    rows: List[CameraCreate]


class BulkUploadCommitResponse(BaseModel):
    inserted: int
    skipped_duplicates: int


# ---------- Stats ----------

class DashboardStats(BaseModel):
    total_cameras: int
    online: int
    offline: int
    maintenance: int
    ageing: int
    synthetic: int
    by_department: dict
    by_camera_type: dict
    by_district: dict
    by_ownership: dict
    by_storage_type: dict
    by_install_year: dict


# ---------- Health ----------

class HealthCameraOut(CameraOut):
    flags: List[str]


class HealthSummary(BaseModel):
    ageing_count: int
    offline_count: int
    maintenance_count: int
    needs_attention_count: int
    expected_service_life_years: int
    items: List[HealthCameraOut]


# ---------- Audit ----------

class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_email: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    details: Optional[str] = None
    timestamp: datetime.datetime


class AuditLogListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AuditLogOut]


# ---------- Coverage ----------

class DistrictCoverageStat(BaseModel):
    district: str
    camera_count: int
    region_area_km2: float
    covered_area_km2: float
    gap_area_km2: float
    coverage_pct: float
