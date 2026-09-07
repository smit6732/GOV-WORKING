#!/usr/bin/env python3
"""
Registers Sentinel Camera Grid cameras into Model 1's own registry, using
the grid's catalogue endpoint — so Model 2 (and the rest of this app) picks
them up automatically through the *same* API/DB Model 1 already exposes.
This script never creates a second camera list; its only job is populating
Model 1's existing `cameras` table via Model 1's existing `/cameras` API,
the same way a human filling out the "Add Camera" form would.

*** FIELD NAMES BELOW ARE BEST-EFFORT, NOT VERIFIED AGAINST A REAL
RESPONSE. *** The Sentinel resource page
(https://sentinel.gujarat.gov.in/resource) describes GET /api/ingest only
in prose — "returns every camera with its id, location, codec, live
status, stream properties, and all three URLs" — it does not publish an
actual JSON schema or the authentication mechanism (likely only visible
once you have real, logged-in grid access). `_first(...)` calls in
map_camera() try several plausible key names so a wrong guess for one
field doesn't break the whole mapping, but they ARE guesses. Run with
--dry-run first, read the printed raw record, and adjust map_camera() to
match reality before registering anything for real.

Usage:
    SENTINEL_BASE_URL=http://<sentinel-host> \
    SENTINEL_API_TOKEN=<token, if the grid needs one>  \
    MODEL1_API_URL=http://localhost:8000 \
    MODEL1_ADMIN_EMAIL=superadmin@gujaratpolice.gov.in \
    MODEL1_ADMIN_PASSWORD=SuperAdmin@123 \
    python scripts/sync_sentinel_cameras.py --dry-run

Drop --dry-run to actually register. Idempotent — already-registered
camera_ids (prefixed "SENTINEL-") are skipped, so it's safe to re-run as
new cameras come online in the grid.

Needs `httpx` (already a backend dependency — e.g. run via
backend/.venv/Scripts/python.exe on the no-Docker dev setup, or
`pip install httpx` for a standalone run).
"""

import argparse
import os
import sys

import httpx

SENTINEL_BASE_URL = os.environ.get("SENTINEL_BASE_URL", "").rstrip("/")
SENTINEL_API_TOKEN = os.environ.get("SENTINEL_API_TOKEN")  # optional bearer token
SENTINEL_INGEST_PATH = os.environ.get("SENTINEL_INGEST_PATH", "/api/ingest")

MODEL1_API_URL = os.environ.get("MODEL1_API_URL", "http://localhost:8000").rstrip("/")
MODEL1_ADMIN_EMAIL = os.environ.get("MODEL1_ADMIN_EMAIL", "superadmin@gujaratpolice.gov.in")
MODEL1_ADMIN_PASSWORD = os.environ.get("MODEL1_ADMIN_PASSWORD", "SuperAdmin@123")

# Registry defaults for fields Sentinel's catalogue likely doesn't carry —
# it's a general traffic/surveillance grid, not built to our schema.
# Adjust once real access shows what's actually present vs. missing.
DEFAULT_DEPARTMENT = os.environ.get("SENTINEL_DEFAULT_DEPARTMENT", "Home Department - Police")
DEFAULT_CAMERA_TYPE = os.environ.get("SENTINEL_DEFAULT_CAMERA_TYPE", "IP Bullet")
DEFAULT_DISTRICT = os.environ.get("SENTINEL_DEFAULT_DISTRICT", "Gandhinagar")
# Gandhinagar city center — used only when a record has no lat/lon, since
# Model 1's POST /cameras rejects coordinates outside Gujarat's bbox.
DEFAULT_LAT = float(os.environ.get("SENTINEL_DEFAULT_LAT", "23.2156"))
DEFAULT_LON = float(os.environ.get("SENTINEL_DEFAULT_LON", "72.6369"))

CAMERA_ID_PREFIX = "SENTINEL-"


def _first(record: dict, *keys, default=None):
    """First present, non-empty key from `keys` — lets one field-name
    guess fail over to the next, since the real response shape isn't
    published anywhere we can read without grid access."""
    for k in keys:
        if k in record and record[k] not in (None, ""):
            return record[k]
    return default


def _is_live(value) -> bool:
    """Sentinel's live/status field could be a bool or a string like
    'live'/'offline' — a bare truthiness check on a string gets this
    wrong ('offline' is a non-empty string, so it's truthy)."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() not in ("false", "0", "offline", "inactive", "down", "")


def fetch_catalogue() -> list:
    if not SENTINEL_BASE_URL:
        sys.exit("SENTINEL_BASE_URL is required, e.g. http://<sentinel-host>")

    headers = {}
    if SENTINEL_API_TOKEN:
        headers["Authorization"] = f"Bearer {SENTINEL_API_TOKEN}"

    url = f"{SENTINEL_BASE_URL}{SENTINEL_INGEST_PATH}"
    print(f"[sentinel-sync] GET {url}")
    resp = httpx.get(url, headers=headers, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()

    # The catalogue might be a bare list, or wrapped — try the plausible shapes.
    if isinstance(data, list):
        cameras = data
    elif isinstance(data, dict):
        cameras = data.get("cameras") or data.get("data") or data.get("items") or []
    else:
        cameras = []

    if not cameras:
        print("[sentinel-sync] WARNING: empty or unrecognized response shape. Raw response:")
        print(data)
    return cameras


def map_camera(record: dict):
    """Maps one Sentinel catalogue record into Model 1's CameraCreate
    shape. *** Adjust the _first(...) key guesses below once you've seen
    a real record. ***"""
    cam_id = _first(record, "id", "camera_id", "stream_id", "streamId")

    rtsp_url = _first(record, "rtsp_url", "rtsp", "rtspUrl")
    if not rtsp_url and isinstance(record.get("urls"), dict):
        rtsp_url = record["urls"].get("rtsp")

    if not cam_id or not rtsp_url:
        print(f"[sentinel-sync] Skipping record with no id/rtsp_url — raw: {record}")
        return None

    lat = _first(record, "latitude", "lat")
    lon = _first(record, "longitude", "lon", "lng")
    location = _first(record, "location", "name", "label", default="")
    live = _is_live(_first(record, "live", "live_status", "status"))

    return {
        "camera_id": f"{CAMERA_ID_PREFIX}{cam_id}",
        "district": DEFAULT_DISTRICT,
        "department": DEFAULT_DEPARTMENT,
        "nearest_station": str(location)[:255] if location else None,
        "camera_type": DEFAULT_CAMERA_TYPE,
        "vendor": "Sentinel Grid",
        "ownership": "Government",
        "latitude": float(lat) if lat is not None else DEFAULT_LAT,
        "longitude": float(lon) if lon is not None else DEFAULT_LON,
        "connectivity_status": "Active" if live else "Offline",
        "rtsp_url": rtsp_url,
        "analytics_capabilities": "anpr",
    }


def get_model1_token() -> str:
    resp = httpx.post(
        f"{MODEL1_API_URL}/auth/login",
        data={"username": MODEL1_ADMIN_EMAIL, "password": MODEL1_ADMIN_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def existing_camera_ids(token: str) -> set:
    resp = httpx.get(
        f"{MODEL1_API_URL}/cameras",
        params={"search": CAMERA_ID_PREFIX, "page_size": 2000},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return {item["camera_id"] for item in resp.json()["items"]}


def register_camera(token: str, payload: dict) -> bool:
    resp = httpx.post(
        f"{MODEL1_API_URL}/cameras",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15.0,
    )
    if resp.status_code == 201:
        return True
    print(f"[sentinel-sync] Failed to register {payload['camera_id']}: {resp.status_code} {resp.text}")
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print what would be registered, don't write anything")
    args = parser.parse_args()

    records = fetch_catalogue()
    print(f"[sentinel-sync] Catalogue returned {len(records)} camera(s)")
    if records:
        print(f"[sentinel-sync] First raw record (for field-name sanity-checking): {records[0]}")

    mapped = [m for m in (map_camera(r) for r in records) if m]
    print(f"[sentinel-sync] {len(mapped)} record(s) mapped to a registerable camera")

    if args.dry_run:
        for m in mapped:
            print(f"[sentinel-sync] DRY RUN would register: {m}")
        return

    token = get_model1_token()
    existing = existing_camera_ids(token)

    registered, skipped = 0, 0
    for payload in mapped:
        if payload["camera_id"] in existing:
            skipped += 1
            continue
        if register_camera(token, payload):
            registered += 1

    print(f"[sentinel-sync] Done — registered {registered}, skipped {skipped} already-present")


if __name__ == "__main__":
    main()
