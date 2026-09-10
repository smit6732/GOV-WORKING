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
    # Model 2 additive fields — absent (null) for the vast majority of the
    # registry, which has no live feed. analytics_capabilities is how Model 2
    # discovers which cameras are ANPR-eligible via this same existing API.
    rtsp_url: Optional[str] = None
    onvif_url: Optional[str] = None
    analytics_capabilities: Optional[str] = None
    # Optional override: a ready-to-use, already-playable HLS URL for this
    # camera (e.g. an external provider's own CDN-served .m3u8), used
    # as-is by the Video Wall instead of assuming every camera's HLS is
    # served through our own MediaMTX. Most cameras leave this null and
    # get the MediaMTX-derived URL, same as before.
    hls_url: Optional[str] = None


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
    rtsp_url: Optional[str] = None
    onvif_url: Optional[str] = None
    analytics_capabilities: Optional[str] = None
    hls_url: Optional[str] = None


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


# ==================== Model 2 — feeds / ANPR search / tags / alerts ====================

class FeedOut(BaseModel):
    camera_id: str
    district: str
    department: str
    nearest_station: Optional[str] = None
    latitude: float
    longitude: float
    rtsp_url: str
    # MediaMTX path name only — the browser builds the actual HLS/WebRTC URL
    # against its own hostname (same convention as any other public port on
    # this stack; the backend doesn't know the browser-facing hostname).
    # Used only when hls_url below is absent.
    stream_path: str
    # A ready-to-use, absolute HLS URL, when the camera has one set
    # (e.g. an external provider's own CDN-served .m3u8) — the Video Wall
    # uses this directly instead of assuming MediaMTX. Null for cameras
    # relying on our own MediaMTX relay (the common case).
    hls_url: Optional[str] = None
    analytics_capabilities: Optional[str] = None
    stream_status: Optional[str] = None  # from ANPR_Standalone's /stream/status, best-effort


class AnprEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    camera_id: str
    event_type: str
    timestamp: datetime.datetime
    track_id: Optional[int] = None
    vehicle_class: Optional[str] = None
    vehicle_bbox: Optional[List[float]] = None
    vehicle_confidence: Optional[float] = None
    plate_no: Optional[str] = None
    plate_confidence: Optional[float] = None
    plate_bbox: Optional[List[float]] = None
    created_at: datetime.datetime
    # joined in from Camera, not stored on the event itself
    district: Optional[str] = None
    department: Optional[str] = None


class AnprEventListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AnprEventOut]


class VehicleHistoryPoint(BaseModel):
    event_id: int
    camera_id: str
    district: Optional[str] = None
    department: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timestamp: datetime.datetime
    plate_no: Optional[str] = None
    plate_confidence: Optional[float] = None
    track_id: Optional[int] = None


class RouteSegment(BaseModel):
    from_camera_id: str
    to_camera_id: str
    route_type: str  # "road_path" (real routing) or "straight_fallback"
    coordinates: List[List[float]]  # [lat, lon] pairs, ready for a Leaflet Polyline
    distance_meters: Optional[float] = None
    duration_seconds: Optional[float] = None


class VehicleHistoryResponse(BaseModel):
    plate_no: str
    points: List[VehicleHistoryPoint]
    segments: List[RouteSegment]


class TaggedPlateCreate(BaseModel):
    plate_no: str = Field(min_length=2, max_length=32)
    reason: Optional[str] = None
    department: Optional[str] = None  # None = global tag (super_admin only)


class TaggedPlateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    plate_no: str
    reason: Optional[str] = None
    department: Optional[str] = None
    tagged_by: Optional[str] = None
    is_active: bool
    created_at: datetime.datetime
    removed_at: Optional[datetime.datetime] = None


class AnprAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_id: int
    camera_id: str
    tagged_plate_id: int
    plate_no: str
    matched_reason: Optional[str] = None
    created_at: datetime.datetime
    district: Optional[str] = None
    department: Optional[str] = None


class AnprAlertListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[AnprAlertOut]
