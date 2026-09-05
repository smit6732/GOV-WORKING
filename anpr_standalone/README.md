# ANPR Metadata Microservice — Model 2 component

**Read this first if you're picking this up in a new Claude Code session.**

## What this is

This is the **ANPR-based metadata generation** piece of a larger "Model 2"
build: a unified CCTV viewing platform that aggregates feeds from multiple
departments' existing VMS systems (via RTSP/ONVIF/vendor APIs) into one
interface, without touching those departments' own infrastructure. Per the
architecture note this came from, Model 2's key features are:

- Feed aggregation (RTSP/ONVIF/vendor APIs)
- **ANPR-based metadata generation** ← this module
- Event tagging and camera-wise indexing
- **Searchable vehicle-movement records** ← this module's `track_id`
- Configurable video walls / multi-camera grids
- Alerts for tagged events/vehicles

Suggested stack: WebRTC/HLS for streaming, ONVIF/RTSP for integration,
Python microservices for backend, Kafka + Elasticsearch + PostgreSQL for
messaging/search. **This module is the "AI/ML: ANPR" piece of that stack**,
shaped as a standalone Python microservice you can point a video source at
and get structured JSON events out of.

## Provenance

The core detection logic (`anpr/plate_recognizer.py`) was extracted and
cleaned up from an existing single-department system ("AI Vigilnet" — a
Flask app combining face recognition + ANPR for one department's own
cameras). In that system, ANPR was just an on-demand function call
(`PlateRecognizer().predict(frame)` behind a `/vehicle/get_number_plate`
route) — no vehicle detection, no tracking, no event schema, no service
layer. Everything in this package beyond `plate_recognizer.py` is new,
built for Model 2's actual requirements:

- `anpr/vehicle_detector.py` — **new**. The original system never detected
  vehicles, only plates. This uses a stock COCO-pretrained YOLOv8n model
  filtered to car/motorcycle/bus/truck.
- `anpr/pipeline.py` — **new**. Associates each plate with the vehicle box
  it falls inside, and (optionally) tracks vehicles across frames so a
  "vehicle movement record" is possible.
- `service/` — **new**. A FastAPI microservice + pluggable output sinks
  (console/JSONL now, Kafka stub ready to enable).

## File manifest

```
anpr/
  plate_recognizer.py   Detects license plates (YOLO) + reads them (PaddleOCR)
  vehicle_detector.py   Detects vehicles (YOLOv8n/COCO) + tracks them (ByteTrack)
  pipeline.py            Combines both into vehicle-movement events
service/
  api.py                 FastAPI microservice (HTTP layer)
  sinks.py                Pluggable event outputs (console, JSONL, Kafka stub)
  static/index.html       Browser demo UI (live webcam + photo upload) — served at /demo
examples/
  process_image.py       CLI demo: one image in, annotated image + JSON out
  process_video_stream.py CLI demo: video/RTSP/webcam in, JSON events out
weights/
  ANPR_YOLO.pt            Custom-trained plate detector (2 classes: plate, military-plate)
  yolov8n.pt              Stock COCO vehicle detector (auto-downloaded if missing)
requirements.txt
```

## Setup

Requires Python 3.10+ (built and tested on 3.12).

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

pip install -r requirements.txt

# torch/torchvision aren't in requirements.txt because the right wheel
# depends on your hardware:
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
# --- OR, if you have an NVIDIA GPU with CUDA 12.1 ---
# pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

### Known gotcha: PaddleOCR crash on some CPUs

Recent `paddlepaddle` CPU builds throw:
```
NotImplementedError: (Unimplemented) ConvertPirAttribute2RuntimeAttribute
not support [pir::ArrayAttribute<pir::DoubleAttribute>]
```
This is already worked around in `plate_recognizer.py` via
`enable_mkldnn=False` on the `PaddleOCR(...)` constructor. If you ever see
this error again (e.g. after a paddlepaddle upgrade), that's the first
thing to check.

### First run downloads models

- PaddleOCR downloads its detection/recognition models (~100–150MB total)
  to `~/.paddlex/official_models/` on first use.
- `facenet`/face stuff is NOT part of this package — that was a different
  part of the source system, deliberately left out since Model 2's brief
  only asks for ANPR.
- `weights/yolov8n.pt` is already included in this folder; if it's ever
  missing, ultralytics re-downloads it automatically (~6MB).

## Usage

### As a library

```python
from anpr.pipeline import ANPRPipeline
import cv2

pipeline = ANPRPipeline(camera_id="gate-cam-01")
frame = cv2.imread("test.jpg")
events = pipeline.process_frame(frame)          # stateless, single frame
# or, for a continuous stream (enables track_id):
events = pipeline.process_frame(frame, track=True)
```

### CLI demos

```bash
python examples/process_image.py path/to/photo.jpg
python examples/process_video_stream.py 0                    # webcam
python examples/process_video_stream.py rtsp://user:pass@host/stream1
```

### As a microservice

```bash
uvicorn service.api:app --host 0.0.0.0 --port 8090
```

- `GET  /health` — status + list of active streams
- `POST /detect/image` — multipart image upload → one-shot JSON events
- `POST /stream/start` — `{"camera_id": "cam-01", "source": "rtsp://...", "target_fps": 2.0}`
  → starts a background thread reading that source, running the tracked
  pipeline, and emitting events to the configured sink (console +
  `anpr_events.jsonl` by default)
- `POST /stream/stop` — `{"camera_id": "cam-01"}`
- `GET  /stream/status` — list active camera_ids

Interactive API docs at `http://localhost:8090/docs` once running.

### Showcase demo page

`http://localhost:8090/demo/` — a self-contained browser page (no build
step) with two tabs:

- **Live Webcam**: starts your camera, samples ~1 frame/sec, overlays
  detection boxes on the live video, logs each detection.
- **Upload Photo**: pick any image of a vehicle/plate, click Detect, see
  boxes + plate text drawn on the photo.

Both just call `/detect/image` — nothing new on the backend. This isn't in
Model 2's brief explicitly (the doc only mentions "ANPR demonstration on
live or recorded feeds" and doesn't call out a photo-upload mode), but a
photo upload is a much more reliable thing to demo live than a webcam or
RTSP feed — no lighting/network dependency, fully repeatable. Worth
keeping even after the real unified-viewer frontend exists, as a fallback
demo path.

## Event schema

Every detection — from the library, the CLI demos, or the service — is a
dict shaped like this (this is what a Kafka message value / Elasticsearch
document / Postgres row should look like downstream):

```json
{
  "event_type": "vehicle_detection",
  "camera_id": "gate-cam-01",
  "timestamp": "2026-09-04T22:40:00.123456+00:00",
  "track_id": 17,
  "vehicle_class": "car",
  "vehicle_bbox": [120, 80, 340, 260],
  "vehicle_confidence": 0.91,
  "plate_no": "MH12AB1234",
  "plate_confidence": 0.87,
  "plate_bbox": [180, 210, 260, 240]
}
```

- `event_type` is `"vehicle_detection"` when a vehicle box was found (plate
  fields are `null` if no plate matched inside it), or
  `"plate_only_detection"` when a plate was found but didn't fall inside
  any detected vehicle box (common on tight/cropped camera angles, or when
  the vehicle detector missed — plates are still reported, just without
  vehicle-level fields).
- `track_id` is only populated when the pipeline was called with
  `track=True` on a continuous stream (i.e. via `/stream/start` or
  `examples/process_video_stream.py`) — this is the field to key
  "vehicle movement record" queries on.
- `timestamp` is ISO-8601 UTC.

## Wiring into the rest of Model 2

- **Kafka**: `service/sinks.py` has a commented-out `KafkaSink` — uncomment,
  `pip install kafka-python`, and swap it into `service/api.py`'s `_sink =
  MultiSink(...)` line. Suggested topic: `anpr.vehicle-events`, keyed by
  `camera_id` to preserve per-camera ordering.
- **Elasticsearch**: index the event dicts as-is; `camera_id`, `plate_no`,
  and `track_id` are the fields you'll want to search/filter on for
  "searchable vehicle-movement records."
- **PostgreSQL**: flatten the same dict into a table
  (`camera_id, ts, track_id, vehicle_class, vehicle_bbox, vehicle_conf,
  plate_no, plate_conf, plate_bbox`) if you want relational queries instead
  of/alongside Elasticsearch.
- **Unified viewer**: the `/stream/start` endpoint's `source` param accepts
  any URL OpenCV can open — including RTSP URLs proxied through whatever
  the aggregation layer settles on for ONVIF/vendor feeds.

## Known limitations / next steps

1. **Plate model is India-oriented.** `ANPR_YOLO.pt` only distinguishes
   `plate` vs `military-plate`; OCR cleanup assumes 4–15 alphanumeric
   characters with at least one digit. If Model 2 needs to handle other
   plate formats, that logic is in
   `PlateRecognizer._clean_plate_text()`.
2. **Vehicle detector is generic, not fine-tuned.** YOLOv8n/COCO gets
   car/motorcycle/bus/truck boxes but wasn't trained on this deployment's
   actual camera angles/lighting. Expect to swap in a fine-tuned model
   later if accuracy matters for a specific site.
3. **Tracking is per-process, in-memory.** `VehicleDetector.track()` uses
   ultralytics' built-in ByteTrack, which only tracks within one
   continuous call sequence on one `VehicleDetector` instance. The service
   already creates one `ANPRPipeline` (and thus one tracker) per
   `camera_id` in `/stream/start`, which is correct — just don't share one
   `ANPRPipeline` across multiple cameras.
4. **No re-identification across camera restarts or between cameras.** If
   "vehicle movement records" need to link the same physical vehicle seen
   by two different cameras, that's a separate re-ID problem (plate number
   match is the practical proxy for that here — `plate_no` is comparable
   across cameras even though `track_id` isn't).
5. **CPU-only tested.** Runs fine on CPU (a few FPS depending on hardware);
   if a GPU is available, install the CUDA torch wheel (see Setup) and
   both detectors will pick it up automatically (`torch.cuda.is_available()`
   check in both `PlateRecognizer` and `VehicleDetector`).
