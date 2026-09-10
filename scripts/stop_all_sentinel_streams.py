#!/usr/bin/env python3
"""
Stops every currently-running ANPR stream at once, via ANPR_Standalone's
POST /stream/stop_all. Previously there was no bulk-stop capability at
all -- only a one-camera-at-a-time /stream/stop -- so stopping a full
30-camera grid meant either 30 individual calls or just leaving them
running. Useful at the end of a testing session, or before restarting
the backend if you don't want it immediately restarting everything
again on its own next boot.

Usage:
    python scripts/stop_all_sentinel_streams.py
    ANPR_SERVICE_URL=http://localhost:8090 python scripts/stop_all_sentinel_streams.py

No credentials needed -- this only talks to our own ANPR service
(exposed on localhost:8090 by default), not the Sentinel grid directly.

Needs `httpx` (already a backend dependency).
"""

import os

import httpx

ANPR_SERVICE_URL = os.environ.get("ANPR_SERVICE_URL", "http://localhost:8090").rstrip("/")


def main():
    resp = httpx.post(f"{ANPR_SERVICE_URL}/stream/stop_all", timeout=15.0)
    resp.raise_for_status()
    data = resp.json()
    count = data.get("count", 0)
    camera_ids = data.get("camera_ids", [])
    if count == 0:
        print("[stop-all-sentinel] No active streams to stop.")
        return
    print(f"[stop-all-sentinel] Stopping {count} stream(s): {', '.join(camera_ids)}")


if __name__ == "__main__":
    main()
