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

from collections import defaultdict
from datetime import datetime, timezone

import cv2

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

    def __init__(
        self,
        camera_id: str = "unknown",
        vehicle_conf: float = 0.4,
        plate_conf: float = 0.45,
        zoom_rescan: bool = True,
        zoom_pad_frac: float = 0.15,
        zoom_min_height: int = 300,
        zoom_max_scale: float = 8.0,
        zoom_rescan_conf_threshold: float = 0.7,
    ):
        self.camera_id = camera_id
        self.vehicle_detector = VehicleDetector(conf_threshold=vehicle_conf)
        self.plate_recognizer = PlateRecognizer(conf_threshold=plate_conf)

        # Second-pass "zoomed" plate re-detection: on a wide-angle camera a
        # distant vehicle can be only a few dozen pixels tall, which is too
        # little effective resolution for a single whole-frame plate-detector
        # pass to pick up -- or the plate gets *found* but at low confidence
        # with a misread. When the whole-frame pass either misses the
        # vehicle's plate entirely, or found one but with no OCR read or
        # confidence below zoom_rescan_conf_threshold, crop just that
        # vehicle out of the ORIGINAL full-resolution frame, upscale the
        # crop, and run plate detection again on it alone -- the same
        # model, just given more pixels to work with for that one region.
        # The better of the two results (prefer a non-null plate_no, then
        # higher confidence) is kept. Real-data-driven: on the actual
        # Sentinel grid footage, vehicle detection succeeds at moderate
        # confidence but the plate detector almost never fires at all, and
        # confirmed by direct testing: a whole-frame pass that DOES find a
        # plate at low confidence can still misread it where the zoomed
        # pass reads it correctly at much higher confidence -- so this
        # can't be gated on "found nothing" alone.
        self.zoom_rescan = zoom_rescan
        self.zoom_pad_frac = zoom_pad_frac
        self.zoom_min_height = zoom_min_height
        self.zoom_max_scale = zoom_max_scale
        self.zoom_rescan_conf_threshold = zoom_rescan_conf_threshold

        # Real-data finding (Sentinel Grid, 2026-09-10): a meaningful share
        # of plate detections are static scene elements re-detected every
        # frame at the exact same fixed pixel location -- burned-in
        # timestamp overlays, business/phone-number decals, camera-
        # housing fixtures -- not real vehicle plates. Cross-checked
        # directly against our own DB: OCR output on some of the
        # "successful" reads included things like a phone number and what
        # reads as a burned-in HH:MM:SS timestamp -- text that is real,
        # but is not a plate. Worse, one such static false positive
        # (misread as "GJ11CH2") ended up attached to over a dozen
        # different tracked vehicles, because it happened to sit inside
        # whichever vehicle's box was passing by -- so this isn't only an
        # "orphaned detection" problem. A genuine moving vehicle's plate
        # changes screen position frame to frame; a static false positive
        # doesn't. Track how many times each (quantized) screen location
        # has produced a plate detection and stop reporting it once it's
        # clearly not attached to anything that moves, instead of
        # reporting the same non-plate object forever.
        self._static_location_hits = defaultdict(int)
        self._STATIC_LOCATION_GRID = 20  # px bucket size for "same" location
        self._STATIC_LOCATION_SUPPRESS_AFTER = 4

    @staticmethod
    def _better_plate(a, b):
        """Pick the better of two plate detections (either may be None):
        prefer one with an actual OCR read over one without, then prefer
        higher confidence."""
        if a is None:
            return b
        if b is None:
            return a
        if bool(a.get("plate_no")) != bool(b.get("plate_no")):
            return a if a.get("plate_no") else b
        return a if a["confidence"] >= b["confidence"] else b

    # ---------------------------------------------------------------
    def _zoomed_plate_for_vehicle(self, frame, vehicle_bbox):
        """Crop `vehicle_bbox` (+ padding) out of `frame`, upscale it, and
        run the plate detector on just that crop. Returns a detection dict
        with its bbox translated back into the ORIGINAL frame's coordinate
        space (so callers/overlays don't need to know this happened), or
        None if nothing was found."""
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = vehicle_bbox
        bw, bh = x2 - x1, y2 - y1
        if bw <= 0 or bh <= 0:
            return None

        pad_x, pad_y = int(bw * self.zoom_pad_frac), int(bh * self.zoom_pad_frac)
        cx1, cy1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
        cx2, cy2 = min(w, x2 + pad_x), min(h, y2 + pad_y)
        if cx2 <= cx1 or cy2 <= cy1:
            return None

        crop = frame[cy1:cy2, cx1:cx2]
        crop_h = crop.shape[0]
        if crop_h == 0:
            return None

        scale = min(self.zoom_max_scale, max(1.0, self.zoom_min_height / crop_h))
        if scale > 1.0:
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        # precise=True: this is already the "spend extra effort" pass --
        # a small fraction of total frames, exactly where the slower but
        # more accurate OCR model (see plate_recognizer.py's ocr_precise)
        # is worth its cost.
        detections = self.plate_recognizer.predict(crop, precise=True)["detections"]
        if not detections:
            return None

        # Prefer a detection that actually has plate text over merely the
        # highest-confidence box (a confident box with a failed OCR read
        # is worth less than a slightly-less-confident box that read).
        best = next((d for d in detections if d.get("plate_no")), detections[0])
        bx1, by1, bx2, by2 = best["bbox"]
        return {
            **best,
            "bbox": (
                int(bx1 / scale) + cx1, int(by1 / scale) + cy1,
                int(bx2 / scale) + cx1, int(by2 / scale) + cy1,
            ),
        }

    # ---------------------------------------------------------------
    def _drop_static_locations(self, plates):
        """Filter out plate detections at a screen location that keeps
        firing frame after frame — scene clutter (a burned-in timestamp
        overlay, a business/phone-number decal, a camera-housing fixture),
        not a real vehicle's plate. Applied to the whole-frame detection
        list BEFORE vehicle-matching, so a static false positive that
        happens to sit inside a passing vehicle's box (observed on real
        footage: the same fixed-location misread attached to over a dozen
        different tracked vehicles) gets caught too, not just the
        unmatched/orphaned case."""
        kept = []
        for p in plates:
            bx1, by1, bx2, by2 = p["bbox"]
            loc_key = (
                ((bx1 + bx2) // 2) // self._STATIC_LOCATION_GRID,
                ((by1 + by2) // 2) // self._STATIC_LOCATION_GRID,
            )
            self._static_location_hits[loc_key] += 1
            if self._static_location_hits[loc_key] <= self._STATIC_LOCATION_SUPPRESS_AFTER:
                kept.append(p)
        return kept

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
        plates = self._drop_static_locations(self.plate_recognizer.predict(frame)["detections"])

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

            needs_rescan = self.zoom_rescan and (
                plate is None
                or not plate.get("plate_no")
                or plate["confidence"] < self.zoom_rescan_conf_threshold
            )
            if needs_rescan:
                # Whole-frame pass either missed this vehicle's plate
                # entirely, or found one with no OCR read / low confidence
                # -- try again on a cropped, upscaled version of just its
                # region, and keep whichever result is actually better
                # rather than assuming the zoomed pass automatically wins.
                zoomed = self._zoomed_plate_for_vehicle(frame, v["bbox"])
                plate = self._better_plate(plate, zoomed)

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
        # — still worth reporting rather than silently dropping (static
        # scene clutter at a fixed location was already filtered out of
        # `plates` above, for both this loop and the vehicle-matched one).
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
