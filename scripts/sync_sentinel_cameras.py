#!/usr/bin/env python3
"""
Pulls the Sentinel Camera Grid's own catalogue (GET /api/ingest, per the
official hackathon resource page's "Consuming the Sentinel Camera Grid"
guide) and uses it to:
  1. Register any camera in the catalogue that isn't already in our
     registry (same as before), and
  2. Fill in `hls_url` on cameras we already have, so the Video Wall can
     finally show real browser video for them (previously only ANPR
     tracking worked against real Sentinel cameras -- no browser preview,
     since we never had a ready-to-use HLS URL for them).

/api/ingest requires an authenticated session -- confirmed directly (an
unauthenticated request 302-redirects to /auth/login). This script never
logs in on your behalf: you log into the portal yourself in your own
browser, then hand this script your session cookie via an environment
variable, same as the RTSP credentials before.

*** FIELD NAMES IN map_camera() BELOW ARE BEST-EFFORT. *** The resource
page describes the catalogue's content in prose ("every camera with its
id, location, codec, live status, stream properties, and all three
URLs") but doesn't publish an exact JSON schema. Run with --discover
first -- it prints the raw first record and exits without touching
anything -- and fix map_camera()'s _first(...) key guesses to match
reality before running for real.

How to get your session cookie:
  1. Log into https://cctv.corp8.cloud in your normal browser.
  2. Open DevTools (F12) -> Network tab.
  3. Reload the page, click any request to cctv.corp8.cloud.
  4. In Request Headers, find "Cookie:" and copy its ENTIRE value
     (e.g. "session=eyJhbGc...; other_cookie=abc123").
  5. Use it exactly as SENTINEL_SESSION_COOKIE below -- paste the whole
     string, semicolons and all.

Usage:
    SENTINEL_BASE_URL=https://cctv.corp8.cloud \
    SENTINEL_SESSION_COOKIE="session=...; ..." \
    python scripts/sync_sentinel_cameras.py --discover

    SENTINEL_BASE_URL=https://cctv.corp8.cloud \
    SENTINEL_SESSION_COOKIE="session=...; ..." \
    MODEL1_ADMIN_PASSWORD=SuperAdmin@123 \
    python scripts/sync_sentinel_cameras.py --dry-run

Drop --dry-run to actually register/update. Idempotent -- new cameras
are registered, already-registered ones only get hls_url filled in (if
currently empty; never overwrites a working rtsp_url), safe to re-run.

Needs `httpx` (already a backend dependency).
"""

import argparse
import os
import sys

import httpx

SENTINEL_BASE_URL = os.environ.get("SENTINEL_BASE_URL", "").rstrip("/")
SENTINEL_SESSION_COOKIE = os.environ.get("SENTINEL_SESSION_COOKIE")  # e.g. "session=...; other=..."
SENTINEL_AUTH_BEARER = os.environ.get("SENTINEL_AUTH_BEARER")  # alternative, if it turns out to be token-based
SENTINEL_INGEST_PATH = os.environ.get("SENTINEL_INGEST_PATH", "/api/ingest")

MODEL1_API_URL = os.environ.get("MODEL1_API_URL", "http://localhost:8000").rstrip("/")
MODEL1_ADMIN_EMAIL = os.environ.get("MODEL1_ADMIN_EMAIL", "superadmin@gujaratpolice.gov.in")
MODEL1_ADMIN_PASSWORD = os.environ.get("MODEL1_ADMIN_PASSWORD", "SuperAdmin@123")

DEFAULT_DEPARTMENT = os.environ.get("SENTINEL_DEFAULT_DEPARTMENT", "Home Department - Police")
DEFAULT_CAMERA_TYPE = os.environ.get("SENTINEL_DEFAULT_CAMERA_TYPE", "IP PTZ")
DEFAULT_DISTRICT = os.environ.get("SENTINEL_DEFAULT_DISTRICT", "Ahmedabad")
DEFAULT_LAT = float(os.environ.get("SENTINEL_DEFAULT_LAT", "23.0225"))
DEFAULT_LON = float(os.environ.get("SENTINEL_DEFAULT_LON", "72.5714"))

CAMERA_ID_PREFIX = "SENTINEL-"


def _first(record: dict, *keys, default=None):
    for k in keys:
        if k in record and record[k] not in (None, ""):
            return record[k]
    return default


def _is_live(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() not in ("false", "0", "offline", "inactive", "down", "")


def _sentinel_headers() -> dict:
    headers = {}
    if SENTINEL_SESSION_COOKIE:
        headers["Cookie"] = SENTINEL_SESSION_COOKIE
    if SENTINEL_AUTH_BEARER:
        headers["Authorization"] = f"Bearer {SENTINEL_AUTH_BEARER}"
    return headers


def fetch_catalogue() -> list:
    if not SENTINEL_BASE_URL:
        sys.exit("SENTINEL_BASE_URL is required, e.g. https://cctv.corp8.cloud")
    if not SENTINEL_SESSION_COOKIE and not SENTINEL_AUTH_BEARER:
        sys.exit(
            "SENTINEL_SESSION_COOKIE (or SENTINEL_AUTH_BEARER) is required -- "
            "/api/ingest requires a logged-in session. See the usage note at "
            "the top of this file for how to get your session cookie."
        )

    url = f"{SENTINEL_BASE_URL}{SENTINEL_INGEST_PATH}"
    print(f"[sentinel-sync] GET {url}")
    resp = httpx.get(url, headers=_sentinel_headers(), timeout=30.0, follow_redirects=False)

    if resp.status_code in (301, 302, 303, 307, 308):
        sys.exit(
            f"[sentinel-sync] Got redirected to {resp.headers.get('location')} -- "
            "your session cookie is missing, wrong, or expired. Log in again and "
            "grab a fresh Cookie header value."
        )
    resp.raise_for_status()
    data = resp.json()

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


def _clean_location_name(raw: str) -> str:
    """Confirmed real shape from /cameras.json (a lighter UI-list helper,
    not necessarily the same endpoint as /api/ingest): {"id": "cam01",
    "name": "01 Chiman bhai Bridge"} -- strip the leading ordinal number
    Sentinel prefixes onto its own display name, we don't need it."""
    parts = raw.strip().split(" ", 1)
    if len(parts) == 2 and parts[0].isdigit():
        return parts[1]
    return raw.strip()


def map_camera(record: dict):
    """Maps one Sentinel catalogue record into our CameraCreate/update
    shape. Confirmed real minimal shape (from /cameras.json): just
    {"id", "name"} -- no coordinates, live status, codec, or URLs. The
    _first(...) guesses below are kept in case /api/ingest specifically
    (the endpoint the resource page actually documents) turns out to
    return the richer shape it promises; if not, we fall back to
    constructing URLs from the documented pattern."""
    url_id = _first(record, "id", "camera_id", "stream_id", "streamId")
    if not url_id:
        print(f"[sentinel-sync] Skipping record with no id -- raw: {record}")
        return None
    url_id = str(url_id)  # ORIGINAL case -- URL paths are case-sensitive, keep as-is here.

    # Confirmed real catalogue ids are lowercase ("cam01"), but our
    # already-registered cameras use uppercase ("SENTINEL-CAM01", set by
    # register_sentinel_cameras.py). Only OUR camera_id gets normalized;
    # url_id (above) stays whatever case the catalogue actually uses, so
    # constructed URLs still point at the real path.
    cam_id = url_id.upper()

    rtsp_url = _first(record, "rtsp_url", "rtsp", "rtspUrl")
    if not rtsp_url and isinstance(record.get("urls"), dict):
        rtsp_url = record["urls"].get("rtsp")

    hls_url = _first(record, "hls_url", "hls", "hlsUrl")
    if not hls_url and isinstance(record.get("urls"), dict):
        hls_url = record["urls"].get("hls")
    if not hls_url and SENTINEL_BASE_URL:
        # Documented pattern from the resource page's protocol table.
        hls_url = f"{SENTINEL_BASE_URL}/live/stream/{url_id}/index.m3u8"

    whep_url = _first(record, "whep_url", "whep", "webrtc_url")
    if not whep_url and isinstance(record.get("urls"), dict):
        whep_url = record["urls"].get("whep")

    lat = _first(record, "latitude", "lat")
    lon = _first(record, "longitude", "lon", "lng")
    raw_name = _first(record, "location", "name", "label", default="")
    location = _clean_location_name(str(raw_name)) if raw_name else ""
    codec = _first(record, "codec", "video_codec", default="")
    live = _is_live(_first(record, "live", "live_status", "status"))

    return {
        "camera_id": f"{CAMERA_ID_PREFIX}{cam_id}",
        "district": DEFAULT_DISTRICT,
        "department": DEFAULT_DEPARTMENT,
        "nearest_station": location[:255] if location else "Sentinel Grid",
        "camera_type": DEFAULT_CAMERA_TYPE,
        "vendor": "Sentinel Sandbox",
        "ownership": "Government",
        "latitude": float(lat) if lat is not None else DEFAULT_LAT,
        "longitude": float(lon) if lon is not None else DEFAULT_LON,
        "connectivity_status": "Active" if live else "Offline",
        "rtsp_url": rtsp_url,
        "hls_url": hls_url,
        "analytics_capabilities": "anpr",
        "_codec": codec,  # informational only, not sent to our API
        "_whep_url": whep_url,  # informational only -- no WHEP field in our schema yet
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


def existing_cameras(token: str) -> dict:
    """camera_id -> full existing record (so we can decide what, if
    anything, needs updating without clobbering a working rtsp_url)."""
    resp = httpx.get(
        f"{MODEL1_API_URL}/cameras",
        params={"search": CAMERA_ID_PREFIX, "page_size": 2000},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return {item["camera_id"]: item for item in resp.json()["items"]}


def register_camera(token: str, payload: dict) -> bool:
    body = {k: v for k, v in payload.items() if not k.startswith("_")}
    resp = httpx.post(
        f"{MODEL1_API_URL}/cameras", json=body,
        headers={"Authorization": f"Bearer {token}"}, timeout=15.0,
    )
    if resp.status_code == 201:
        return True
    print(f"[sentinel-sync] Failed to register {payload['camera_id']}: {resp.status_code} {resp.text}")
    return False


GENERIC_STATION_PLACEHOLDER = "Sentinel Grid"  # what register_sentinel_cameras.py sets by default


def update_camera_fields(token: str, existing_id: int, camera_id: str, fields: dict) -> bool:
    resp = httpx.put(
        f"{MODEL1_API_URL}/cameras/{existing_id}", json=fields,
        headers={"Authorization": f"Bearer {token}"}, timeout=15.0,
    )
    if resp.status_code == 200:
        return True
    print(f"[sentinel-sync] Failed to update {camera_id}: {resp.status_code} {resp.text}")
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--discover", action="store_true",
                         help="Fetch and print the raw catalogue response, then exit. Touches nothing.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would change, don't write anything")
    args = parser.parse_args()

    records = fetch_catalogue()
    print(f"[sentinel-sync] Catalogue returned {len(records)} camera(s)")
    if records:
        print(f"[sentinel-sync] First raw record:\n{records[0]}\n")

    if args.discover:
        print("[sentinel-sync] --discover: stopping here. Compare the raw record above against "
              "map_camera()'s _first(...) key guesses and adjust if needed, then re-run without --discover.")
        return

    mapped = [m for m in (map_camera(r) for r in records) if m]
    print(f"[sentinel-sync] {len(mapped)} record(s) mapped to a registerable camera")

    if args.dry_run:
        for m in mapped:
            shown = {k: v for k, v in m.items() if not k.startswith("_")}
            print(f"[sentinel-sync] DRY RUN would register/update: {shown}")
        return

    token = get_model1_token()
    existing = existing_cameras(token)

    registered, updated, skipped = 0, 0, 0
    for payload in mapped:
        cam_id = payload["camera_id"]
        existing_row = existing.get(cam_id)

        if existing_row is None:
            if register_camera(token, payload):
                registered += 1
            continue

        # Already registered -- fill in hls_url if currently empty, and
        # replace the generic "Sentinel Grid" nearest_station placeholder
        # with the catalogue's real location name if we have one better.
        # Never touch rtsp_url here: ours is already proven working.
        update_fields = {}
        if not existing_row.get("hls_url") and payload.get("hls_url"):
            update_fields["hls_url"] = payload["hls_url"]
        if (
            existing_row.get("nearest_station") == GENERIC_STATION_PLACEHOLDER
            and payload.get("nearest_station")
            and payload["nearest_station"] != GENERIC_STATION_PLACEHOLDER
        ):
            update_fields["nearest_station"] = payload["nearest_station"]

        if update_fields:
            if update_camera_fields(token, existing_row["id"], cam_id, update_fields):
                updated += 1
                continue
        skipped += 1

    print(f"[sentinel-sync] Done — registered {registered} new, updated {updated} with hls_url, "
          f"skipped {skipped} (already complete)")


if __name__ == "__main__":
    main()
