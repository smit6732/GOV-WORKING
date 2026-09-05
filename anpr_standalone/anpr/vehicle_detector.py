"""
General vehicle detector (car / motorcycle / bus / truck).

The original project only ever detected plates directly — it had no
vehicle-level detection. This module adds that half using a stock,
COCO-pretrained YOLOv8n model (auto-downloaded by ultralytics on first
use, ~6MB), filtered down to vehicle classes.
"""

import os

import torch
from ultralytics import YOLO

# COCO class ids for vehicle-like classes.
VEHICLE_CLASS_IDS = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_VEHICLE_MODEL_PATH = os.path.join(BASE_DIR, "..", "weights", "yolov8n.pt")


class VehicleDetector:
    def __init__(self, model_path: str = None, conf_threshold: float = 0.4):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.conf_threshold = conf_threshold
        # ultralytics downloads yolov8n.pt automatically the first time
        # this runs, if it isn't already cached at this path.
        actual_model_path = model_path if model_path else DEFAULT_VEHICLE_MODEL_PATH
        self.model = YOLO(actual_model_path).to(self.device)

    def predict(self, frame):
        """
        Detect vehicles in `frame`.

        Returns a list of {"bbox": (x1, y1, x2, y2), "confidence": float,
        "class_name": "car" | "motorcycle" | "bus" | "truck"}.
        """
        if frame is None or frame.size == 0:
            return []

        results = self.model(frame, verbose=False, classes=list(VEHICLE_CLASS_IDS))
        boxes = results[0].boxes

        detections = []
        for box in boxes:
            conf = float(box.conf[0])
            if conf < self.conf_threshold:
                continue

            class_id = int(box.cls[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            detections.append({
                "bbox": (x1, y1, x2, y2),
                "confidence": conf,
                "class_name": VEHICLE_CLASS_IDS.get(class_id, str(class_id)),
            })

        return detections

    def track(self, frame):
        """
        Same as predict(), but assigns a persistent `track_id` to each
        vehicle so it can be followed across frames.

        IMPORTANT: call this on every frame of ONE continuous stream, in
        order (persist=True keeps ByteTrack's internal state alive
        between calls). Don't interleave frames from different cameras
        through the same VehicleDetector instance — use one instance
        per camera/stream.
        """
        if frame is None or frame.size == 0:
            return []

        results = self.model.track(
            frame, verbose=False, persist=True,
            classes=list(VEHICLE_CLASS_IDS), tracker="bytetrack.yaml",
        )
        boxes = results[0].boxes

        detections = []
        for box in boxes:
            conf = float(box.conf[0])
            if conf < self.conf_threshold:
                continue
            if box.id is None:
                continue  # track not yet confirmed by the tracker

            class_id = int(box.cls[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            detections.append({
                "bbox": (x1, y1, x2, y2),
                "confidence": conf,
                "class_name": VEHICLE_CLASS_IDS.get(class_id, str(class_id)),
                "track_id": int(box.id[0]),
            })

        return detections
