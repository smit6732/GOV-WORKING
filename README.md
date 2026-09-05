# GOV-WORKING — Gujarat CCTV GIS Registry & Unified Viewing Platform

**Model 1 — Centralised CCTV Registry & GIS Mapping.**
A metadata and asset-visibility layer for CCTV cameras deployed across Gujarat Police
jurisdictions: where cameras are, who owns them, and what they are — camera CRUD, GIS
mapping, coverage/gap analysis, RBAC, and audit logging. Untouched by Model 2 below.

**Model 2 — Unified CCTV Viewing Platform**, built on top of Model 1's registry (see
[`MODEL2_ARCHITECTURE.md`](MODEL2_ARCHITECTURE.md) for the full design): live feed
aggregation (MediaMTX), an ANPR (automatic number-plate recognition) pipeline built on
the vendored `anpr_standalone/` microservice, a Kafka → Postgres/Elasticsearch event
pipeline, plate tagging with real-time alerts, and a searchable vehicle-movement
dashboard — all added as new tables/routers/pages inside the same app, reading Model
1's camera data through its existing API rather than duplicating it.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite + Tailwind CSS + React-Leaflet + Recharts + hls.js |
| Backend | Python FastAPI + SQLAlchemy + JWT auth + aiokafka |
| Database | PostgreSQL 16 + PostGIS 3.4 |
| Model 2 infra | Kafka (KRaft), Elasticsearch, MediaMTX, ANPR_Standalone (YOLOv8 + PaddleOCR + ByteTrack) |
| Orchestration | Docker Compose |

## Quick start (Docker)

Requires Docker Desktop.

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend Swagger docs: http://localhost:8000/docs
- Postgres: localhost:5432 (`cctv` / `cctv_pass` / `cctv_registry`)
- ANPR_Standalone service (Model 2): http://localhost:8090 · own demo page at `/demo/`
- MediaMTX (Model 2): RTSP `:8554`, HLS `:8888`, WebRTC `:8889`
- Kafka (Model 2): `:9092` · Elasticsearch (Model 2): `:9200`

Model 2's two mock camera feeds (`CAM-M2-001`, `CAM-M2-002`) need real footage dropped
at `media/department_a.mp4` / `media/department_b.mp4` to show live video — see
[`media/README.md`](media/README.md). Everything else (ANPR live demo panel, search,
tags, alerts) works without them.

## Quick start (no Docker — verified working, Model 1 only)

The full Model 1 stack was verified end-to-end on this machine without Docker, against a
real local PostgreSQL 17 + PostGIS 3.6 install (Windows service `postgresql-17`,
superuser password `cctv_pass`; app role/db `cctv` / `cctv_pass` / `cctv_registry`, same
as the Docker setup). To run it this way again:

```bash
# Backend (from backend/, using the venv already set up there)
cd backend
DATABASE_URL="postgresql://cctv:cctv_pass@localhost:5432/cctv_registry" \
DATA_DIR="../data" \
.venv/Scripts/python -m uvicorn app.main:app --port 8001

# Frontend (from frontend/, in a separate terminal)
cd frontend
VITE_API_PROXY_TARGET="http://localhost:8001" npm run dev -- --port 5173
```

- Frontend: http://localhost:5173
- Backend Swagger docs: http://localhost:8001/docs

(Port 8000 was avoided during verification because something on this machine held it in
a `Bound`, non-listening state — 8001 worked cleanly. Use whichever's free for you and
adjust `VITE_API_PROXY_TARGET` to match.)

Model 2's extra pieces (Kafka, Elasticsearch, MediaMTX, ANPR_Standalone) aren't part of
this no-Docker path — the backend degrades gracefully without them (logs a warning,
keeps serving Model 1 normally) but Video Wall / Search / Tags / Alerts need the full
`docker compose up` stack.

On first boot the backend creates the schema and seeds:
- 697 real Gujarat police station locations from `data/police_stations_gujarat.csv` (reference geodata only — not treated as cameras)
- 2,090 synthetic demo camera records from `data/demo_cctv_cameras.csv`, all persisted with `is_synthetic = true` and shown in the UI with a "Demo / Synthetic" badge
- 3 demo user accounts (see below)
- 2 Model 2 demo cameras (`CAM-M2-001`, `CAM-M2-002`) carrying `rtsp_url` and `analytics_capabilities="anpr"`, one per department for RBAC testing

Seeding is idempotent per-row, so it's safe to restart the stack.

## Demo accounts (RBAC)

| Role | Email | Password | Scope |
|---|---|---|---|
| Super Admin | `superadmin@gujaratpolice.gov.in` | `SuperAdmin@123` | Full read/write across all departments, audit logs, user scope |
| Department Admin | `deptadmin@gujaratpolice.gov.in` | `DeptAdmin@123` | Read/write limited to "Home Department - Police" cameras only |
| Viewer | `viewer@gujaratpolice.gov.in` | `Viewer@123` | Read-only across the whole registry |

These are seeded for demo purposes — change/rotate them (and `JWT_SECRET` in
`docker-compose.yml`) before any real deployment.

## Features

### Model 1 — Registry

1. **Login + RBAC** — JWT auth, three roles enforced both in the API (403s on
   out-of-scope writes) and the UI (tabs/buttons hidden per role).
2. **Dashboard** — live totals (total/online/offline/maintenance/ageing/synthetic),
   department/type/district/year breakdowns — all computed from the database, no
   hardcoded numbers.
3. **GIS Map** — Leaflet map of Gujarat with every camera as a marker, colour-coded by
   connectivity status, filterable by department / camera type / district / status.
4. **Camera Registry** — paginated, filterable, searchable table with edit/delete
   (role-gated) and CSV export.
5. **Add Camera** — form-based create with Gujarat bounding-box validation.
6. **Bulk Upload** — CSV upload → server-side validation → preview (valid rows +
   itemised row errors) → explicit commit step. Test it with `data/demo_cctv_cameras.csv`.
7. **Coordinates** — stored as native PostGIS `POINT(EPSG:4326)`; `GET /cameras/geojson`
   exposes the map layer.
8. **Health & Ageing** — flags cameras whose install year puts them past the configured
   expected service life (default 7 years) and cameras currently `Offline`/`Maintenance`.
9. **Coverage & Gap Analysis** — per-district PostGIS pipeline
   (`ST_ConvexHull` of stations → `ST_Buffer` jurisdiction region, `ST_Buffer` +
   `ST_Union` of camera points → covered area, `ST_Difference` → gap), rendered as
   green/red polygon layers on the map with an adjustable coverage-radius slider, plus
   a per-district stats table.
10. **CSV export** — camera registry export and gap-analysis report, both filter-aware.
11. **Audit log** — every camera create/update/delete/bulk-upload and login is recorded
    with who/what/when; viewable (role-scoped) under Audit Logs.
12. **Swagger docs** — auto-generated at `/docs` on the backend.

### Model 2 — Unified CCTV Viewing Platform

13. **Video Wall** — one unified grid: real camera tiles pulled from Model 1's registry
    (`GET /feeds`, filtered to `analytics_capabilities` containing `"anpr"`), played via
    HLS (hls.js) relayed through MediaMTX, side by side with a **live ANPR demo panel**
    ("My Webcam" with camera-select/switch, and "Upload Photo") that captures a frame and
    POSTs it directly to the vendored ANPR_Standalone service for real-time
    vehicle/plate detection with bbox overlay.
14. **ANPR pipeline on real feeds** — the backend calls ANPR_Standalone's `/stream/start`
    at boot for every analytics-capable camera, running the same vendored
    detection/tracking pipeline (YOLOv8 vehicle detector → custom plate-YOLO → PaddleOCR
    → ByteTrack) continuously against the live RTSP feed.
15. **Event pipeline** — every detection event (ANPR_Standalone's own
    `vehicle_detection` / `plate_only_detection` JSON schema, unmodified) flows through
    Kafka (`anpr.vehicle-events`) to two independent consumers: an in-process one that
    writes to Postgres, checks tagged plates, and pushes live alerts over WebSocket, and
    a standalone one that indexes into Elasticsearch for search.
16. **Vehicle Search** — search by plate / camera / department / time range
    (Elasticsearch-backed), plus a movement-history route map per plate/track (Postgres
    join back to Model 1's camera coordinates).
17. **Tags & Alerts** — operators tag a plate of interest; when it's next detected on any
    ANPR-tracked feed, an alert fires instantly (live WebSocket push) and is recorded to
    history and the audit log.

## Architecture

**Model 1:**

```
CSV / Manual Entry / Bulk Upload
            │
            ▼
      FastAPI (JWT/RBAC, validation, PostGIS queries)
            │
            ▼
   PostgreSQL + PostGIS  (Camera POINT geometry, PoliceStation, User, AuditLog)
            │
            ▼
   GeoJSON / REST endpoints
            │
            ▼
   React + Leaflet + Recharts dashboard (Vite build, served by nginx, proxies /api → backend)
```

**Model 2** (see [`MODEL2_ARCHITECTURE.md`](MODEL2_ARCHITECTURE.md) for the full
diagram and data-flow trace):

```
Departmental VMS (mock feed loop, or a real camera in production)
            │  RTSP
            ▼
        MediaMTX  ──── HLS/WebRTC ────────────────────────► Video Wall (browser)
            │  RTSP pull
            ▼
   ANPR_Standalone (vendored, unmodified detection/tracking)
   YOLOv8 vehicle → plate YOLO → PaddleOCR → ByteTrack
            │  JSON events
            ▼
        Kafka (anpr.vehicle-events)
        ┌───────────────┴───────────────┐
        ▼                               ▼
  Consumer A (in-process)        Consumer B (own container)
  → Postgres anpr_events          → Elasticsearch anpr_events
  → tag match → alert + WS push   → powers Vehicle Search
```

The webcam/photo Live Demo panel is a separate, simpler path: the browser calls
ANPR_Standalone's `/detect/image` directly (bypassing the backend, Kafka, and both
databases entirely) for a one-shot detection with no persistence.

## Repository layout

```
data/                          seed CSVs (mounted read-only into the backend container)
backend/
  app/
    main.py                    FastAPI app, router registration, startup seed hook
    config.py                  settings (DB URL, JWT secret, thresholds, Model 2 endpoints)
    database.py                SQLAlchemy engine/session
    models.py                  User, Camera, PoliceStation, AuditLog + Model 2: AnprEvent, TaggedPlate, AnprAlert
    schemas.py                 Pydantic request/response models
    auth.py                    JWT + password hashing + RBAC dependencies
    utils.py                   geometry helpers, ageing logic, audit log writer, department scoping
    seed.py                    idempotent CSV + Model 2 demo-camera seeding on startup
    anpr_client.py             Model 2: orchestrates ANPR_Standalone's /stream/start
    es_client.py               Model 2: Elasticsearch client + index management
    ws_manager.py               Model 2: WebSocket connection manager for live alerts
    workers/
      consumer_a.py             Model 2: in-process Kafka consumer (Postgres + alerts + WS)
      consumer_es.py            Model 2: standalone Kafka consumer (Elasticsearch indexer)
    routers/
      auth.py                  /auth/login, /auth/me
      cameras.py                /cameras CRUD, /cameras/geojson, /cameras/export, bulk upload
      stats.py                  /stats/dashboard
      health.py                  /health/ageing
      coverage.py                /coverage/gap-analysis (+ /export)
      audit.py                   /audit-logs
      stations.py                 /stations/geojson (reference layer)
      feeds.py                     Model 2: /feeds (ANPR-eligible cameras + stream status)
      anpr_search.py                Model 2: /vehicles/search, /vehicles/{plate}/history, /anpr-events
      tags.py                        Model 2: /tags, /alerts
frontend/
  src/
    pages/                     Dashboard, GISMap, CameraRegistry, AddCamera, BulkUpload,
                                Health, Coverage, AuditLogs, Login,
                                VideoWall, VehicleSearch, Tags, Alerts (Model 2)
    context/AuthContext.jsx    JWT session state
    components/                Layout/nav, route guards, shared UI atoms, MapBase (shared map)
    hooks/useAlertsSocket.js   Model 2: reconnecting WebSocket hook for live alerts
anpr_standalone/                Model 2: vendored ANPR microservice (YOLOv8 + PaddleOCR + ByteTrack) — see its own README.md
mediamtx/mediamtx.yml           Model 2: feed-aggregation config (RTSP in, HLS/WebRTC out)
feed-loop/                      Model 2: mock departmental-VMS ffmpeg publisher image
media/                          Model 2: user-supplied mock feed footage (gitignored .mp4s)
MODEL2_ARCHITECTURE.md          Model 2 design note + data-flow diagram
docker-compose.yml
```

## Notes / limitations (by design)

- `demo_cctv_cameras.csv` is synthetic test data anchored near real station coordinates;
  every seeded row is flagged `is_synthetic = true` in the schema and carries a purple
  "Demo / Synthetic" badge in the UI. Cameras added through the UI or bulk upload after
  seeding are marked `is_synthetic = false`.
- Coverage/gap analysis approximates each district's jurisdiction as a buffered convex
  hull of its police stations (no official Gujarat administrative boundary shapefile was
  provided) — good enough to visualize relative gaps, not a legal boundary.
- "Ageing" is based on `install_year` vs. a configurable expected service life
  (`EXPECTED_SERVICE_LIFE_YEARS`, default 7); "offline beyond threshold" is approximated
  as any camera currently `Offline`, since no continuous uptime telemetry exists in a
  metadata-only registry.
- Model 2's two mock departmental feeds and the single MediaMTX instance playing both
  "departmental VMS" and "aggregation relay" roles are documented, deliberate
  simplifications for this build — see `MODEL2_ARCHITECTURE.md`.
- ANPR accuracy depends on the footage supplied (lighting, angle, resolution, distance)
  — this is inherent to the vendored detection/OCR models, not a configurable setting.
