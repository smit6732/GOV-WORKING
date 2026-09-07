"""
Minimal ANPR microservice for the Model 2 unified-viewer platform.

Endpoints:
  GET  /health
  POST /detect/image           -- multipart image upload, one-shot detection
  POST /stream/start           -- start background tracking on an RTSP/video/webcam source
  POST /stream/stop            -- stop a running stream by camera_id
  GET  /stream/status          -- list active streams

Run:
    uvicorn service.api:app --host 0.0.0.0 --port 8090

This is intentionally thin — it exists to prove the anpr/ package out
as a real HTTP service and to give the rest of Model 2 (the unified
viewer / dashboard) something to call and something to consume events
from (anpr_events.jsonl by default; swap in service/sinks.py's
KafkaSink for production).
"""

import os
import threading
import time

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from anpr.pipeline import ANPRPipeline
from service.sinks import ConsoleSink, JSONLFileSink, KafkaSink, MultiSink

# Force RTSP over TCP for every cv2.VideoCapture opened via the FFmpeg
# backend in this process. Real camera infrastructure (as opposed to our
# own local mock feeds) is commonly reached over networks where UDP RTSP
# drops/reorders packets; TCP trades a little latency for reliability.
# Must be set before any VideoCapture is created, so it's done at import
# time here rather than per-call.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

app = FastAPI(title="ANPR Metadata Service")

# The Live Demo Panel (in Model 2's unified viewer) calls this service
# directly from the browser on its own exposed port, so it needs CORS open.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Demo page (webcam + photo-upload detection UI) at /demo — see
# service/static/index.html. Useful for showcasing without waiting on
# the full Model 2 unified-viewer frontend.
app.mount("/demo", StaticFiles(directory="service/static", html=True), name="demo")

# camera_id -> {"thread": Thread, "stop_flag": threading.Event, "pipeline": ANPRPipeline}
_active_streams = {}
_streams_lock = threading.Lock()

# Model 2 wiring: when KAFKA_BOOTSTRAP_SERVERS is set (i.e. running inside
# the full stack), events also go to Kafka; the console/file sinks stay on
# regardless so this module still works exactly as documented when run
# standalone with no broker available.
_kafka_bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS")
if _kafka_bootstrap:
    _sink = MultiSink(ConsoleSink(), KafkaSink(bootstrap_servers=_kafka_bootstrap))
else:
    _sink = MultiSink(ConsoleSink(), JSONLFileSink("anpr_events.jsonl"))

# A stateless pipeline for one-shot /detect/image calls (no tracking).
_image_pipeline = ANPRPipeline(camera_id="ad-hoc-upload")


@app.get("/", include_in_schema=False)
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/demo/")


@app.get("/health")
def health():
    with _streams_lock:
        active = list(_active_streams.keys())
    return {"status": "ok", "active_streams": active}


@app.post("/detect/image")
async def detect_image(file: UploadFile = File(...)):
    contents = await file.read()
    npimg = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode image")

    events = _image_pipeline.process_frame(frame, track=False)
    return {"events": events}


class StartStreamRequest(BaseModel):
    camera_id: str
    source: str  # RTSP URL, video file path, or webcam index as a string ("0")
    target_fps: float = 2.0


@app.post("/stream/start")
def start_stream(req: StartStreamRequest):
    with _streams_lock:
        if req.camera_id in _active_streams:
            raise HTTPException(status_code=409, detail=f"Stream '{req.camera_id}' already running")

        stop_flag = threading.Event()
        pipeline = ANPRPipeline(camera_id=req.camera_id)
        thread = threading.Thread(
            target=_run_stream,
            args=(req.camera_id, req.source, req.target_fps, pipeline, stop_flag),
            daemon=True,
        )
        _active_streams[req.camera_id] = {"thread": thread, "stop_flag": stop_flag, "pipeline": pipeline}
        thread.start()

    return {"status": "started", "camera_id": req.camera_id}


class StopStreamRequest(BaseModel):
    camera_id: str


@app.post("/stream/stop")
def stop_stream(req: StopStreamRequest):
    with _streams_lock:
        entry = _active_streams.pop(req.camera_id, None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No active stream '{req.camera_id}'")
    entry["stop_flag"].set()
    return {"status": "stopping", "camera_id": req.camera_id}


@app.get("/stream/status")
def stream_status():
    with _streams_lock:
        return {"active_streams": list(_active_streams.keys())}


# Reconnect backoff bounds for a source that never opens or drops mid-stream.
_RECONNECT_MIN_DELAY = 2.0
_RECONNECT_MAX_DELAY = 30.0
# A handful of consecutive failed reads is treated as a transient hiccup
# (worth a short sleep and another try on the SAME capture); beyond that,
# the capture is released and reopened with backoff — a genuinely dropped
# connection usually never recovers just by keeps calling .read() on it.
_CONSECUTIVE_FAILURE_LIMIT = 5


def _run_stream(camera_id: str, source: str, target_fps: float, pipeline: ANPRPipeline, stop_flag: threading.Event):
    """Background worker: reads frames, runs the pipeline, emits events to the
    sink. Reconnects with exponential backoff (2s -> 30s cap) whenever the
    source never opens or drops mid-stream, instead of hanging forever or
    giving up after one failed attempt — real camera infrastructure (unlike
    our own always-on mock feeds) can be briefly unreachable at any time."""
    src = int(source) if source.isdigit() else source
    interval = 1.0 / target_fps
    last = 0.0
    backoff = _RECONNECT_MIN_DELAY
    consecutive_failures = 0

    print(f"[anpr-service] Streaming started for camera '{camera_id}' ({source})")
    cap = cv2.VideoCapture(src)
    try:
        while not stop_flag.is_set():
            if not cap.isOpened():
                cap.release()
                print(
                    f"[anpr-service] Could not open source for camera '{camera_id}': "
                    f"{source} — retrying in {backoff:.0f}s"
                )
                if stop_flag.wait(backoff):
                    break
                backoff = min(backoff * 2, _RECONNECT_MAX_DELAY)
                cap = cv2.VideoCapture(src)
                continue

            ret, frame = cap.read()
            if not ret:
                consecutive_failures += 1
                if consecutive_failures < _CONSECUTIVE_FAILURE_LIMIT:
                    time.sleep(0.5)
                    continue
                cap.release()
                print(
                    f"[anpr-service] Lost connection for camera '{camera_id}' "
                    f"after {consecutive_failures} failed reads — reconnecting in {backoff:.0f}s"
                )
                if stop_flag.wait(backoff):
                    break
                backoff = min(backoff * 2, _RECONNECT_MAX_DELAY)
                cap = cv2.VideoCapture(src)
                consecutive_failures = 0
                continue

            consecutive_failures = 0
            backoff = _RECONNECT_MIN_DELAY

            now = time.time()
            if now - last < interval:
                continue
            last = now

            for event in pipeline.process_frame(frame, track=True):
                _sink.emit(event)
    finally:
        cap.release()
        print(f"[anpr-service] Streaming stopped for camera '{camera_id}'")
