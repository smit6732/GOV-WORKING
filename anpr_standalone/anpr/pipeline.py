"""
Combines vehicle detection + plate detection/OCR into structured
"vehicle movement" events — the unit of data this module hands off
to whatever sits downstream (Kafka topic, Postgres table,
Elasticsearch index, etc. per the Model 2 architecture).

Two modes:
  - process_frame(frame):            stateless, per-frame detections
  - process_frame(frame, track=True): frame is part of a continuous
                                       stream; vehicles get a stable
                                       track_id across calls (needed
                                       for "searchable vehicle
                                       movement records")

Tracking uses ultralytics' built-in ByteTrack/BoT-SORT integration
(model.track(..., persist=True)) — no extra tracking library needed.
Call track=True on every frame of the SAME stream, in order; don't
mix frames from different cameras into one ANPRPipeline instance
when tracking (create one ANPRPipeline per camera instead).
"""

from datetime import datetime, timezone

from .plate_recognizer import PlateRecognizer
from .vehicle_detector import VehicleDetector


def _plate_inside_vehicle(plate_bbox, vehicle_bbox, min_overlap: float = 0.5) -> bool:
    """True if `plate_bbox` sits mostly inside `vehicle_bbox`."""
    px1, py1, px2, py2 = plate_bbox
    vx1, vy1, vx2, vy2 = vehicle_bbox

    x1, y1 = max(px1, vx1), max(py1, vy1)
    x2, y2 = min(px2, vx2), min(py2, vy2)
    if x2 <= x1 or y2 <= y1:
        return False

    intersection = (x2 - x1) * (y2 - y1)
    plate_area = (px2 - px1) * (py2 - py1)
    if plate_area <= 0:
        return False

    return (intersection / plate_area) >= min_overlap


class ANPRPipeline:
    """One instance per camera/video source (tracking state is per-instance)."""

    def __init__(self, camera_id: str = "unknown", vehicle_conf: float = 0.4, plate_conf: float = 0.45):
        self.camera_id = camera_id
        self.vehicle_detector = VehicleDetector(conf_threshold=vehicle_conf)
        self.plate_recognizer = PlateRecognizer(conf_threshold=plate_conf)

    # ---------------------------------------------------------------
    def process_frame(self, frame, track: bool = False, frame_ts: str = None):
        """
        Run vehicle + plate detection on one frame and return a list
        of event dicts (see README.md for the schema).

        track=True: use persistent tracking IDs (call this repeatedly,
        in order, on frames from the SAME video/RTSP source).
        """
        ts = frame_ts or datetime.now(timezone.utc).isoformat()

        vehicles = (
            self.vehicle_detector.track(frame) if track
            else self.vehicle_detector.predict(frame)
        )
        plates = self.plate_recognizer.predict(frame)["detections"]

        events = []
        matched = set()

        for v in vehicles:
            plate = next(
                (p for i, p in enumerate(plates)
                 if i not in matched and _plate_inside_vehicle(p["bbox"], v["bbox"])),
                None,
            )
            if plate is not None:
                matched.add(plates.index(plate))

            events.append({
                "event_type": "vehicle_detection",
                "camera_id": self.camera_id,
                "timestamp": ts,
                "track_id": v.get("track_id"),
                "vehicle_class": v["class_name"],
                "vehicle_bbox": v["bbox"],
                "vehicle_confidence": v["confidence"],
                "plate_no": plate["plate_no"] if plate else None,
                "plate_confidence": plate["confidence"] if plate else None,
                "plate_bbox": plate["bbox"] if plate else None,
            })

        # Plates the vehicle detector didn't have a matching box for
        # (missed detection, tight crop, two-wheeler edge case, etc.)
        # — still worth reporting rather than silently dropping.
        for i, p in enumerate(plates):
            if i in matched:
                continue
            events.append({
                "event_type": "plate_only_detection",
                "camera_id": self.camera_id,
                "timestamp": ts,
                "track_id": None,
                "vehicle_class": None,
                "vehicle_bbox": None,
                "vehicle_confidence": None,
                "plate_no": p["plate_no"],
                "plate_confidence": p["confidence"],
                "plate_bbox": p["bbox"],
            })

        return events
