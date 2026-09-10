# Testing Commands — Sentinel Grid Live Integration

Quick reference for running the ANPR pipeline against real Sentinel Camera
Grid footage and checking results. Assumes the full stack is already up
(`docker compose up -d --build`) and you're in the repo root unless noted.

## Register real cameras

The script that actually works is `scripts/register_sentinel_cameras.py`
— it builds every camera's RTSP URL from your Sentinel login credentials
plus a camera number (`rtsp://<user>:<pass>@103.250.160.189:8554/stream/camNN`),
and registers all of them into Model 1's own camera registry.

(`scripts/sync_sentinel_cameras.py` also exists, pulling from Sentinel's
`/api/ingest` catalogue — its response schema was never confirmed against
a real call, so it isn't the proven path. Use `register_sentinel_cameras.py`.)

**You must supply your own Sentinel credentials** — never hardcode them
in a file, never ask an AI assistant to enter them anywhere. Percent-
encoding of `@` in the email is handled for you automatically.

PowerShell:
```powershell
$env:SENTINEL_EMAIL = "you@example.com"
$env:SENTINEL_PASSWORD = "your-sentinel-password"
python scripts/register_sentinel_cameras.py
```

bash:
```bash
SENTINEL_EMAIL=you@example.com SENTINEL_PASSWORD=your-password \
python scripts/register_sentinel_cameras.py
```

Add `--dry-run` to preview without writing anything. Safe to re-run —
already-registered cameras are skipped. Defaults to registering
`SENTINEL-CAM01`..`SENTINEL-CAM30`; override count with
`SENTINEL_CAMERA_COUNT`.

## Start ANPR streaming

**There is no script to run for this.** Streaming starts automatically
when the backend boots — it queries every camera with
`analytics_capabilities` containing `"anpr"` and calls ANPR_Standalone's
`/stream/start` on each one (staggered, and only once ANPR_Standalone is
confirmed ready — see `backend/app/anpr_client.py`).

If you've just registered new cameras, or want streaming to (re-)start:
```bash
docker compose restart backend
```

## Stop ANPR streaming

```bash
python scripts/stop_all_sentinel_streams.py
```

Stops every currently-running stream via ANPR_Standalone's
`POST /stream/stop_all`. No credentials needed — it only talks to our
own ANPR service. Note: if the backend is still running, it will only
restart streams again on its own next restart, not automatically.

## Check status

**Which cameras are currently streaming (thread exists, may or may not
be actually connected):**
```bash
curl http://localhost:8090/stream/status
```

**Real per-camera connectivity (frames actually flowing right now):**
```bash
curl http://localhost:8090/streams/health
```

**All Docker containers healthy:**
```bash
docker compose ps
```

## Logs

```bash
docker compose logs anpr --tail 30
docker compose logs backend --tail 30
```

## Database queries

**Detection counts per camera, all-time (includes any old/stale data
from before a code change — not always what you want mid-investigation):**
```bash
docker exec cctv_db psql -U cctv -d cctv_registry -c "SELECT camera_id, COUNT(*) as total_events, COUNT(plate_no) as plate_reads FROM anpr_events WHERE camera_id LIKE 'SENTINEL-%' GROUP BY camera_id ORDER BY plate_reads DESC;"
```

**Same, but only events since a given point in time** — use this after
deploying a pipeline change, so old (pre-change) rows don't distort the
picture. Each vehicle track's row is updated in place via majority
voting, so a stale row from before your fix doesn't disappear on its
own:
```bash
docker exec cctv_db psql -U cctv -d cctv_registry -c "SELECT camera_id, COUNT(*) as total_events, COUNT(plate_no) as plate_reads FROM anpr_events WHERE camera_id LIKE 'SENTINEL-%' AND created_at > 'YYYY-MM-DD HH:MM:SS' GROUP BY camera_id ORDER BY plate_reads DESC;"
```

**Actual plate numbers read, most recent first:**
```bash
docker exec cctv_db psql -U cctv -d cctv_registry -c "SELECT camera_id, plate_no, plate_confidence, timestamp FROM anpr_events WHERE plate_no IS NOT NULL ORDER BY timestamp DESC LIMIT 30;"
```

**Split "no plate found" from "plate found but OCR/validation rejected it"
from "successful read"** — useful when accuracy looks off and you need to
know which stage is actually failing:
```bash
docker exec cctv_db psql -U cctv -d cctv_registry -c "
SELECT camera_id,
  COUNT(*) FILTER (WHERE plate_bbox IS NULL) AS no_plate_region_found,
  COUNT(*) FILTER (WHERE plate_bbox IS NOT NULL AND plate_no IS NULL) AS plate_found_but_rejected,
  COUNT(*) FILTER (WHERE plate_no IS NOT NULL) AS plate_read_ok
FROM anpr_events WHERE camera_id LIKE 'SENTINEL-%'
GROUP BY camera_id ORDER BY plate_found_but_rejected DESC;"
```

*(`PGPASSWORD` is not required for these — `docker exec` goes through the
container's local trust auth, not remote password auth.)*

## Quick manual test (no live camera needed)

Browser demo panel, bypasses the database/Kafka entirely — good for a
fast sanity check on a single photo:
```
http://localhost:8090/demo/
```

## OCR failure diagnostics (opt-in, off by default)

To see *why* a detected plate region produced no text — PaddleOCR found
nothing at all vs. found text that our own validation rejected — set
`ANPR_OCR_DEBUG: "1"` on the `anpr` service in `docker-compose.yml`,
rebuild, and watch `docker compose logs anpr` for `[ocr-debug]` lines.
Noisy for normal operation, so it's off by default — turn it back off
(`"0"`) when done investigating.
