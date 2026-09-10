#!/usr/bin/env python3
"""
Registers Sentinel Camera Grid cameras into Model 1's own registry, using
the SAME credentials for every camera (just a different stream path per
camera number) -- rtsp://<user>:<password>@<host>:<port>/stream/camNN.

This is the method that has actually worked in practice, unlike
sync_sentinel_cameras.py (which depends on Sentinel's /api/ingest
catalogue -- its response schema was never confirmed against a real
call, and it was never the path that got real cameras registered). Keep
both: this one for "I have login credentials, register the whole grid",
sync_sentinel_cameras.py for if/when the catalogue endpoint gets
verified.

Credentials are supplied by YOU, the person running this script, via
environment variables -- never hardcoded here and never entered by an
AI assistant on your behalf. This mirrors exactly the manual process
used the first time real cameras were registered on this project.

Usage (PowerShell):
    $env:SENTINEL_EMAIL = "you@example.com"
    $env:SENTINEL_PASSWORD = "your-sentinel-password"
    $env:MODEL1_ADMIN_PASSWORD = "SuperAdmin@123"   # only if changed from default
    python scripts/register_sentinel_cameras.py

Usage (bash):
    SENTINEL_EMAIL=you@example.com SENTINEL_PASSWORD=your-password \
    python scripts/register_sentinel_cameras.py

Add --dry-run to see what would be registered without writing anything.
Idempotent -- already-registered camera_ids are skipped, safe to re-run.

Needs `httpx` (already a backend dependency).
"""

import argparse
import os
import sys
from urllib.parse import quote

import httpx

SENTINEL_EMAIL = os.environ.get("SENTINEL_EMAIL", "")
SENTINEL_PASSWORD = os.environ.get("SENTINEL_PASSWORD", "")
SENTINEL_HOST = os.environ.get("SENTINEL_HOST", "103.250.160.189")
SENTINEL_PORT = os.environ.get("SENTINEL_PORT", "8554")
SENTINEL_CAMERA_COUNT = int(os.environ.get("SENTINEL_CAMERA_COUNT", "30"))
SENTINEL_STREAM_PATH_PREFIX = os.environ.get("SENTINEL_STREAM_PATH_PREFIX", "stream/cam")

MODEL1_API_URL = os.environ.get("MODEL1_API_URL", "http://localhost:8000").rstrip("/")
MODEL1_ADMIN_EMAIL = os.environ.get("MODEL1_ADMIN_EMAIL", "superadmin@gujaratpolice.gov.in")
MODEL1_ADMIN_PASSWORD = os.environ.get("MODEL1_ADMIN_PASSWORD", "SuperAdmin@123")

DEFAULT_DISTRICT = os.environ.get("SENTINEL_DEFAULT_DISTRICT", "Ahmedabad")
DEFAULT_DEPARTMENT = os.environ.get("SENTINEL_DEFAULT_DEPARTMENT", "Home Department - Police")
DEFAULT_LAT = float(os.environ.get("SENTINEL_DEFAULT_LAT", "23.0225"))
DEFAULT_LON = float(os.environ.get("SENTINEL_DEFAULT_LON", "72.5714"))

CAMERA_ID_PREFIX = "SENTINEL-"


def build_rtsp_url(cam_num: str) -> str:
    # The @ in an email address MUST be percent-encoded (%40) -- the URL
    # already uses a literal @ to separate credentials from the host, so
    # a second, unencoded @ in the email makes the URL ambiguous to parse
    # (confirmed to cause real connection failures when this was missed).
    user = quote(SENTINEL_EMAIL, safe="")
    return f"rtsp://{user}:{SENTINEL_PASSWORD}@{SENTINEL_HOST}:{SENTINEL_PORT}/{SENTINEL_STREAM_PATH_PREFIX}{cam_num}"


def build_camera_payloads() -> list:
    payloads = []
    for i in range(1, SENTINEL_CAMERA_COUNT + 1):
        cam_num = f"{i:02d}"
        payloads.append({
            "camera_id": f"{CAMERA_ID_PREFIX}CAM{cam_num}",
            "district": DEFAULT_DISTRICT,
            "department": DEFAULT_DEPARTMENT,
            "nearest_station": "Sentinel Grid",
            "camera_type": "IP PTZ",
            "vendor": "Sentinel Sandbox",
            "ownership": "Government",
            "latitude": DEFAULT_LAT,
            "longitude": DEFAULT_LON,
            "connectivity_status": "Active",
            "rtsp_url": build_rtsp_url(cam_num),
            "analytics_capabilities": "anpr",
        })
    return payloads


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
    print(f"[register-sentinel] Failed to register {payload['camera_id']}: {resp.status_code} {resp.text}")
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print what would be registered, don't write anything")
    args = parser.parse_args()

    if not SENTINEL_EMAIL or not SENTINEL_PASSWORD:
        sys.exit(
            "SENTINEL_EMAIL and SENTINEL_PASSWORD environment variables are required.\n"
            "Set them yourself before running this script -- see the usage note at the "
            "top of this file. They are never read from anywhere else."
        )

    payloads = build_camera_payloads()
    print(f"[register-sentinel] Built {len(payloads)} camera payload(s) for {SENTINEL_HOST}:{SENTINEL_PORT}")

    if args.dry_run:
        for p in payloads:
            redacted = {**p, "rtsp_url": p["rtsp_url"].split("@", 1)[-1]}  # don't print credentials
            print(f"[register-sentinel] DRY RUN would register: {redacted}")
        return

    token = get_model1_token()
    existing = existing_camera_ids(token)

    registered, skipped = 0, 0
    for payload in payloads:
        if payload["camera_id"] in existing:
            skipped += 1
            continue
        if register_camera(token, payload):
            registered += 1
            print(f"[register-sentinel] Registered {payload['camera_id']}")

    print(f"[register-sentinel] Done — registered {registered}, skipped {skipped} already-present")


if __name__ == "__main__":
    main()
