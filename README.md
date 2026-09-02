# Gujarat CCTV GIS Registry Dashboard

**Model 1 — Centralised CCTV Registry & GIS Mapping.**
A metadata and asset-visibility layer for CCTV cameras deployed across Gujarat Police
jurisdictions. This is **not** a live surveillance system: there is no RTSP streaming,
video recording/storage, facial recognition, or network-credential storage anywhere in
this codebase. It stores and visualizes *where cameras are and what they are*, not
what they see.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite + Tailwind CSS + React-Leaflet + Recharts |
| Backend | Python FastAPI + SQLAlchemy + JWT auth |
| Database | PostgreSQL 16 + PostGIS 3.4 |
| Orchestration | Docker Compose |

## Quick start (Docker)

Requires Docker Desktop.

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend Swagger docs: http://localhost:8000/docs
- Postgres: localhost:5432 (`cctv` / `cctv_pass` / `cctv_registry`)

## Quick start (no Docker — verified working)

The full stack was verified end-to-end on this machine without Docker, against a real
local PostgreSQL 17 + PostGIS 3.6 install (Windows service `postgresql-17`, superuser
password `cctv_pass`; app role/db `cctv` / `cctv_pass` / `cctv_registry`, same as the
Docker setup). To run it this way again:

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

On first boot the backend creates the schema and seeds:
- 697 real Gujarat police station locations from `data/police_stations_gujarat.csv` (reference geodata only — not treated as cameras)
- 2,090 synthetic demo camera records from `data/demo_cctv_cameras.csv`, all persisted with `is_synthetic = true` and shown in the UI with a "Demo / Synthetic" badge
- 3 demo user accounts (see below)

Seeding only runs when the respective table is empty, so it's safe to restart the stack.

## Demo accounts (RBAC)

| Role | Email | Password | Scope |
|---|---|---|---|
| Super Admin | `superadmin@gujaratpolice.gov.in` | `SuperAdmin@123` | Full read/write across all departments, audit logs, user scope |
| Department Admin | `deptadmin@gujaratpolice.gov.in` | `DeptAdmin@123` | Read/write limited to "Home Department - Police" cameras only |
| Viewer | `viewer@gujaratpolice.gov.in` | `Viewer@123` | Read-only across the whole registry |

These are seeded for demo purposes — change/rotate them (and `JWT_SECRET` in
`docker-compose.yml`) before any real deployment.

## Features

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

## Architecture

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

## Repository layout

```
data/                          seed CSVs (mounted read-only into the backend container)
backend/
  app/
    main.py                    FastAPI app, router registration, startup seed hook
    config.py                  settings (DB URL, JWT secret, thresholds)
    database.py                SQLAlchemy engine/session
    models.py                  User, Camera, PoliceStation, AuditLog (PostGIS geometry)
    schemas.py                 Pydantic request/response models
    auth.py                    JWT + password hashing + RBAC dependencies
    utils.py                   geometry helpers, ageing logic, audit log writer
    seed.py                    idempotent CSV seeding on startup
    routers/
      auth.py                  /auth/login, /auth/me
      cameras.py                /cameras CRUD, /cameras/geojson, /cameras/export, bulk upload
      stats.py                  /stats/dashboard
      health.py                  /health/ageing
      coverage.py                /coverage/gap-analysis (+ /export)
      audit.py                   /audit-logs
      stations.py                 /stations/geojson (reference layer)
frontend/
  src/
    pages/                     Dashboard, GISMap, CameraRegistry, AddCamera, BulkUpload,
                                Health, Coverage, AuditLogs, Login
    context/AuthContext.jsx    JWT session state
    components/                Layout/nav, route guards, shared UI atoms
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
