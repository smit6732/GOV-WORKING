# Gujarat CCTV GIS Registry — Setup & Usage Guide

This file is the complete, self-contained guide to what this project is, how it's
built, how to install every dependency, and how to run and use it. `README.md` has a
shorter overview; this document goes deeper.

---

## 1. What this is

**Model 1 — Centralised CCTV Registry & GIS Mapping**, built for a Gujarat Police
hackathon problem statement. It is a **metadata and asset-visibility layer** for CCTV
cameras deployed across Gujarat Police jurisdictions:

- It stores **where** cameras are and **what** they are (location, department, vendor,
  storage type, connectivity status, install date, etc).
- It does **not** stream, record, or analyse video. There is no RTSP integration, no
  video storage, no facial recognition, and no network/IP credential storage anywhere
  in the codebase. Any request to add those is out of scope for this project by design.

---

## 2. Whole-system architecture

```
CSV / Manual Entry / Bulk Upload (UI)
            │
            ▼
   FastAPI backend (JWT auth, RBAC, validation, PostGIS queries)
            │
            ▼
   PostgreSQL + PostGIS  (Camera as POINT(EPSG:4326), PoliceStation, User, AuditLog)
            │
            ▼
   REST + GeoJSON endpoints  (see Swagger UI at /docs)
            │
            ▼
   React + Leaflet + Recharts dashboard (Vite build, served by nginx in Docker,
   proxying /api/* to the backend)
```

### Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS, React-Leaflet, Recharts, React Router, Axios |
| Backend | Python, FastAPI, SQLAlchemy 2.x, GeoAlchemy2, python-jose (JWT), passlib+bcrypt |
| Database | PostgreSQL 16/17 + PostGIS 3.4+ |
| Containerisation | Docker Compose (postgres+postgis, backend, frontend/nginx) |

### Repository layout

```
data/                            Seed CSVs, mounted read-only into the backend container
  police_stations_gujarat.csv    697 real Gujarat police station locations (reference geodata)
  demo_cctv_cameras.csv          2,090 synthetic camera records (is_synthetic=true)

backend/
  Dockerfile
  requirements.txt
  app/
    main.py                      FastAPI app, CORS, router registration, startup seed hook
    config.py                    Settings: DB URL, JWT secret, ageing threshold, coverage radius
    database.py                  SQLAlchemy engine/session/Base
    models.py                    User, Camera, PoliceStation, AuditLog (PostGIS geometry columns)
    schemas.py                   Pydantic request/response models, enum option lists
    auth.py                      Password hashing, JWT create/decode, RBAC dependencies
    utils.py                     Geometry helpers, ageing logic, audit-log writer, bbox check
    seed.py                      Idempotent CSV seeding on startup (users, stations, cameras)
    routers/
      auth.py                    POST /auth/login, GET /auth/me
      cameras.py                 CRUD, /cameras/geojson, /cameras/export, bulk upload preview+commit
      stats.py                   GET /stats/dashboard
      health.py                  GET /health/ageing
      coverage.py                GET /coverage/gap-analysis (+ /export) — the PostGIS pipeline
      audit.py                   GET /audit-logs
      stations.py                GET /stations/geojson (reference layer)

frontend/
  Dockerfile
  nginx.conf                     Serves the built SPA, proxies /api/ → backend:8000/
  vite.config.js
  src/
    main.jsx, App.jsx            Router entry, route tree, role-gated routes
    api.js                       Axios instance with JWT interceptor
    context/AuthContext.jsx      Login/logout/session state
    components/                  Layout/nav, route guards (RequireAuth/RequireRole), shared UI atoms
    pages/
      Login.jsx
      Dashboard.jsx               Live stat cards + Recharts breakdowns
      GISMap.jsx                  Leaflet map, camera markers, filters
      CameraRegistry.jsx          Paginated/filterable table, inline edit modal, CSV export
      AddCamera.jsx                Create-camera form
      BulkUpload.jsx               CSV upload → validate/preview → commit
      Health.jsx                   Ageing/offline/maintenance flags
      Coverage.jsx                  PostGIS gap-analysis map + per-district table
      AuditLogs.jsx                 Who/what/when log viewer

docker-compose.yml
README.md
SETUP_AND_USAGE_GUIDE.md         This file
```

---

## 3. Installing every dependency

You have two ways to run this: **Docker** (simplest, one command) or **local/no-Docker**
(what was actually used to verify this build end-to-end on Windows). Both are documented
below, in full.

### 3a. Docker path — what you need installed

- **Docker Desktop** (includes Docker Engine + Docker Compose v2). That's the only
  prerequisite — Postgres, PostGIS, Python, Node, and every package are all installed
  automatically inside the containers when you run `docker compose up --build`.

```bash
docker compose up --build
```

This single command:
1. Pulls `postgis/postgis:16-3.4` and starts Postgres with the PostGIS extension baked in.
2. Builds the backend image (`python:3.12-slim` + everything in `backend/requirements.txt`).
3. Builds the frontend image (`node:20-alpine` to build the Vite app, then `nginx:1.27-alpine`
   to serve it and reverse-proxy `/api/*` to the backend).
4. On backend startup, creates the PostGIS extension, creates all tables, and seeds the
   3 demo users + both CSVs (idempotent — safe to restart).

Once it's up:
- Frontend: **http://localhost:3000**
- Backend Swagger/OpenAPI docs: **http://localhost:8000/docs**
- Postgres (if you want to inspect it directly): `localhost:5432`, db `cctv_registry`,
  user `cctv`, password `cctv_pass`

### 3b. Local (no Docker) path — every dependency, one at a time

This is the exact path used to verify the whole stack works, on Windows, without Docker.

**Step 1 — PostgreSQL 17 with PostGIS 3.6**

1. Download the Windows installer from EnterpriseDB:
   `https://get.enterprisedb.com/postgresql/postgresql-17.11-3-windows-x64.exe`
   (if a plain download is blocked by their CDN, add a normal browser `User-Agent` and
   `Referer` header to the request — a bare `curl`/script request can get a 403 from
   their WAF, a browser-like request does not).
2. Run it (`--mode unattended --superpassword <your-choice> --servicename postgresql-17
   --serverport 5432 --disable-components stackbuilder` for a silent install). This
   installs PostgreSQL as a Windows service and starts it automatically.
3. Download the matching PostGIS bundle for your PG version from
   `https://download.osgeo.org/postgis/windows/pg17/` (pick the `postgis-bundle-pgXX-*.zip`
   for your version). Unzip it.
4. Merge the bundle's `bin/`, `lib/`, and `share/extension/` (and `gdal-data/` if present)
   folders **into** your PostgreSQL install directory (e.g. `C:\Program Files\PostgreSQL\17\`).
   This requires an elevated (Administrator) copy, since `Program Files` isn't writable
   by a normal user — `robocopy` handles in-use/locked files (like `libssl`/`zlib` that
   Postgres already ships) more gracefully than `Copy-Item`.
5. Create the app database and enable the extension (using `psql` as the `postgres`
   superuser):
   ```sql
   CREATE ROLE cctv LOGIN PASSWORD 'cctv_pass';
   CREATE DATABASE cctv_registry OWNER cctv;
   \c cctv_registry
   CREATE EXTENSION IF NOT EXISTS postgis;
   GRANT ALL ON SCHEMA public TO cctv;
   ```
6. Verify: `SELECT PostGIS_Version();` should return something like
   `3.6 USE_GEOS=1 USE_PROJ=1 USE_STATS=1`.

**Step 2 — Python 3.12 + backend dependencies**

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
.venv/Scripts/python -m pip install -r requirements.txt
```

This installs: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `geoalchemy2`,
`psycopg2-binary`, `shapely`, `python-jose[cryptography]`, `passlib`, `bcrypt`,
`python-multipart`, `pydantic`, `pydantic-settings`, `python-dotenv`, `email-validator`
— everything the backend needs, no other native/system packages required (`psycopg2-binary`
ships its own `libpq`).

**Step 3 — Node.js 20+ + frontend dependencies**

```bash
cd frontend
npm install
```

This installs: `react`, `react-dom`, `react-router-dom`, `axios`, `leaflet`,
`react-leaflet`, `recharts`, plus dev tooling (`vite`, `@vitejs/plugin-react`,
`tailwindcss`, `postcss`, `autoprefixer`).

**Step 4 — Run both servers**

```bash
# Terminal 1 — backend
cd backend
DATABASE_URL="postgresql://cctv:cctv_pass@localhost:5432/cctv_registry" \
DATA_DIR="../data" \
.venv/Scripts/python -m uvicorn app.main:app --port 8001

# Terminal 2 — frontend
cd frontend
VITE_API_PROXY_TARGET="http://localhost:8001" npm run dev -- --port 5173
```

- Frontend: **http://localhost:5173**
- Backend Swagger docs: **http://localhost:8001/docs**

(Port 8000 is the Docker Compose default; 8001 is used here only because something else
on the verification machine held port 8000 — use whichever port is free for you and match
it in `VITE_API_PROXY_TARGET`.)

On first backend startup it will automatically: create the `postgis` extension (if not
already created), create all tables, and seed the 3 demo users + 697 stations + 2090
cameras from the CSVs in `data/`. This only happens once — subsequent restarts skip
seeding because the tables are no longer empty.

---

## 4. How to use it

### Logging in

Three demo accounts are seeded automatically (click a row on the login screen to
autofill it):

| Role | Email | Password | Scope |
|---|---|---|---|
| Super Admin | `superadmin@gujaratpolice.gov.in` | `SuperAdmin@123` | Full read/write, all departments, audit logs |
| Department Admin | `deptadmin@gujaratpolice.gov.in` | `DeptAdmin@123` | Read/write limited to "Home Department - Police" cameras |
| Viewer | `viewer@gujaratpolice.gov.in` | `Viewer@123` | Read-only, whole registry |

**Rotate these before any real deployment** — they're seeded for demo purposes only,
along with `JWT_SECRET` in `docker-compose.yml` / your environment.

### The tabs

- **Dashboard** — live totals (total / online / offline / maintenance / ageing /
  synthetic-demo count) plus breakdowns by department, camera type, district, and
  install year. Nothing here is hardcoded — every number comes from a live query.
- **GIS Map** — every camera as a marker on a Leaflet map of Gujarat, colour-coded by
  connectivity status (green=Active, red=Offline, amber=Maintenance). Filter by
  department, camera type, district, and status; click a marker for details.
- **Camera Registry** — paginated, filterable, searchable table. Super Admin and
  Department Admin see Edit/Delete actions (Department Admin only for their own
  department); Viewer sees a read-only table. "Export CSV" respects the active filters.
- **Add Camera** — form to register a new camera's metadata + location (Super Admin /
  Department Admin only). Coordinates are validated against a Gujarat bounding box.
- **Bulk Upload** — upload a CSV (same columns as `data/demo_cctv_cameras.csv`), see a
  validation preview (valid rows + itemised row errors, duplicate `camera_id` detection)
  before anything is written, then explicitly commit.
- **Health** — cameras flagged `ageing` (install year past the configured expected
  service life, default 7 years), `offline`, or `maintenance`, with filter chips.
- **Coverage & Gap Analysis** — the PostGIS pipeline: per-district jurisdiction
  (buffered convex hull of that district's police stations) minus the union of
  buffered camera-coverage circles = the uncovered gap, rendered as red/green polygons
  on the map with an adjustable per-camera coverage-radius slider, plus a per-district
  stats table and CSV export.
- **Audit Logs** — every camera create/update/delete/bulk-upload action, and every
  login, with who/what/when (Super Admin sees everyone's; Department Admin sees only
  their own).

### The API directly

Every feature above is backed by a real REST/GeoJSON endpoint — see the interactive
Swagger docs at `/docs` on whichever backend URL you're running (e.g.
`http://localhost:8000/docs` for Docker, `http://localhost:8001/docs` for the local
path above). You can authenticate there with `POST /auth/login`, then call any endpoint
with the returned bearer token.

---

## 5. Known data-quality caveat

The seed CSV records `district="ACB"` (and similar non-geographic values like `CID
Crime`, `ATS`) for some Anti-Corruption-Bureau / specialised-unit cameras instead of a
real Gujarat district. Because the coverage/gap-analysis pipeline builds each
"district's" jurisdiction as a convex hull of its police stations, a scattered
pseudo-district like `ACB` produces an enormous (and not geographically meaningful)
hull — this is a property of the source data, not a bug in the PostGIS logic itself.
