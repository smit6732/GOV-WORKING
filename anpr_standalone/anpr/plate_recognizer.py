"""
License-plate detector + OCR reader.

Extracted and cleaned up from the original AI Vigilnet project's
Processor/ANPR.py. Logic is unchanged: a custom-trained YOLO model
finds plate regions, each crop is enhanced with classic OpenCV
preprocessing, then PaddleOCR reads the text.

Model: weights/ANPR_YOLO.pt — 2 classes: "plate", "military-plate".
This model detects PLATES ONLY, not vehicles. Combine with
vehicle_detector.py if you also want vehicle bounding boxes.
"""

import os
import re
import threading

import cv2
import torch
from paddleocr import PaddleOCR
from ultralytics import YOLO

# Standard Indian plate shape: 2 letters (state) + 2 digits (RTO code) +
# 1-2 letters (series) + 4 digits (unique number), e.g. GJ01AB1234. Used
# only to catch a common OCR confusion -- a digit misread as a
# similar-looking letter, or vice versa (e.g. "GJ32AG2B83", B instead of
# 8) -- in reads that are clearly attempting this exact shape. Deliberately
# scoped to length 9-10-11 only (see _LENGTH_GATED below), so it never
# rejects other legitimate formats this pipeline also needs to accept
# (BH-series, military, short commercial plates) that don't fit this
# pattern.
#
# Kept intentionally STRICT (exactly 2 digits for the RTO code, 1-2
# letters for the series) -- a real-data-driven looser variant
# ([0-9]{1,2} / [A-Z]{1,3}) was tried and directly confirmed via testing
# to RE-ACCEPT "GJ0THR1079", one of the original garbled reads this
# validation exists to reject in the first place. Strictness is the
# point here, not permissiveness.
_STANDARD_PLATE_RE = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}$")

# This pattern can only ever match a 9 or 10 character string (2+2+[1,2]+4).
# The validation used to only run AT length 9/10 -- meaning an 11-character
# garbled read (e.g. OCR inserting one spurious character) skipped the
# check entirely and passed through as if it were fine. Confirmed directly
# on real Sentinel Grid data: "FGUD1AA6035", "FGUO1AK6035", "F0101AH5035"
# -- three different 11-character non-plate reads from the same real
# vehicle within 4 seconds, none caught. Adding 11 to this tuple is safe
# specifically BECAUSE the pattern above mathematically cannot match
# length 11 -- every 11-char string gets rejected, with no risk of
# accidentally loosening what counts as a valid 9/10-length plate.
_LENGTH_GATED = (9, 10, 11)

# Classic OCR letter/digit look-alike confusions. Used only to CORRECT a
# read that's already the right LENGTH for the standard shape but fails
# the strict match by exactly this kind of confusion in one or two
# positions -- not to rescue arbitrary garbage. A length-11 read is never
# correctable this way (that's an extra/missing character, not a
# lookalike substitution) and isn't attempted.
_LETTER_TO_DIGIT = {"O": "0", "I": "1", "S": "5", "B": "8", "Z": "2"}
_DIGIT_TO_LETTER = {v: k for k, v in _LETTER_TO_DIGIT.items()}
# More than this many substitutions in one read is far more likely to be
# genuine noise than a couple of unlucky character misreads -- don't
# force-fit real garbage into a plate shape.
_MAX_CORRECTIONS = 2


def _expected_position_types(length):
    """'L'/'D' per position for the standard plate shape at this length
    (9 = 1-letter series "LLDDLDDDD", 10 = 2-letter series
    "LLDDLLDDDD"). None for any other length -- the standard shape only
    exists at 9 or 10 characters."""
    if length == 9:
        return "LLDDLDDDD"
    if length == 10:
        return "LLDDLLDDDD"
    return None


def _try_correct_plate(text):
    """Given a read that _STANDARD_PLATE_RE already rejected, try fixing
    it via known OCR look-alike confusions in the positions that are the
    wrong type (a letter where a digit is expected, or vice versa).
    Returns the corrected string if it now cleanly matches the standard
    shape within _MAX_CORRECTIONS substitutions, else None (falls back to
    outright rejection, same as before this existed)."""
    expected = _expected_position_types(len(text))
    if expected is None:
        return None

    corrected = list(text)
    corrections = 0
    for i, (ch, want) in enumerate(zip(text, expected)):
        if want == "L" and not ch.isalpha():
            if ch not in _DIGIT_TO_LETTER:
                return None
            corrected[i] = _DIGIT_TO_LETTER[ch]
            corrections += 1
        elif want == "D" and ch.isalpha():
            if ch not in _LETTER_TO_DIGIT:
                return None
            corrected[i] = _LETTER_TO_DIGIT[ch]
            corrections += 1

    if corrections == 0 or corrections > _MAX_CORRECTIONS:
        # 0 corrections would mean the original already matched the
        # standard shape, which means _STANDARD_PLATE_RE would already
        # have accepted it -- this function is only called after that
        # check failed, so this is just a defensive no-op guard.
        return None

    result = "".join(corrected)
    return result if _STANDARD_PLATE_RE.match(result) else None

# When a plate REGION is detected (the YOLO stage succeeds) but no plate_no
# ends up on the event, the cause could be any of: PaddleOCR's own text
# detector finding zero regions in the crop, empty rec_texts on a
# non-empty result, or real OCR text that _clean_plate_text() rejects.
# These are very different problems (crop quality vs. our own validation
# being too strict) and were previously indistinguishable from outside —
# _apply_ocr just returned None for all three. Gated behind an env var so
# it's opt-in diagnostic noise, not a permanent production log spam.
_OCR_DEBUG = os.environ.get("ANPR_OCR_DEBUG", "0") == "1"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_YOLO_PATH = os.path.join(BASE_DIR, "..", "weights", "ANPR_YOLO.pt")


class SingletonType(type):
    """Thread-safe singleton so the (heavy) models load only once per process."""

    _instances = {}
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                cls._instances[cls] = super(SingletonType, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class PlateRecognizer(metaclass=SingletonType):
    """Detects license plates in a frame and OCRs the plate text."""

    def __init__(self, yolo_path=None, conf_threshold: float = 0.45):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.conf_threshold = conf_threshold

        actual_yolo_path = yolo_path if yolo_path else DEFAULT_YOLO_PATH
        self.yolo = YOLO(actual_yolo_path).to(self.device)

        # PaddleOCR downloads its default detection/recognition models to a
        # local cache (~/.paddlex) automatically on first use.
        #
        # enable_mkldnn=False works around a crash on some CPUs with recent
        # paddlepaddle builds: "NotImplementedError: (Unimplemented)
        # ConvertPirAttribute2RuntimeAttribute not support
        # [pir::ArrayAttribute<pir::DoubleAttribute>]" thrown from the
        # oneDNN backend. If your CPU doesn't hit that error you can drop
        # this flag for a small speed gain.
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang="en",
            det_db_thresh=0.3,
            det_db_box_thresh=0.5,
            rec_batch_num=6,
            enable_mkldnn=False,
            # PaddleOCR's default pipeline runs full-page doc-orientation
            # classification + UVDoc unwarping before text detection — built
            # for scanned document pages, not a small plate crop. Confirmed
            # via direct inspection that this stage runs even on plate-sized
            # crops; when it misjudges orientation on a tiny/noisy crop, the
            # whole crop gets rotated before detection, so the returned box
            # coordinates come back in the POST-rotation frame — inverting a
            # two-line plate's row order relative to the original image
            # (both rows read correctly, just top/bottom swapped). Disabling
            # it removes that failure mode; per-textline orientation
            # (use_angle_cls) stays on since that corrects individual
            # characters, not whole-crop layout.
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
        )

        # A second, more accurate but slower OCR instance, used ONLY for
        # the zoom-rescan pass (pipeline.py's _zoomed_plate_for_vehicle) --
        # not the routine per-frame pass. PP-OCRv6 (above) tops out at its
        # "medium" tier; there is no PP-OCRv6 "server" tier. PP-OCRv5 does
        # have one, and it's a genuinely more capable model, confirmed via
        # a controlled side-by-side test on identical synthetic input:
        # v6_medium misread "GJ01AB1234" as "GJO1AB1234" (0/O confusion)
        # in 0.39s; v5_server read it perfectly correct in 0.90s (~2.3x
        # slower). Given real, hard-won CPU-contention problems this
        # session (32 concurrent streams starving even trivial requests),
        # unconditionally swapping every OCR call to the slower model
        # isn't worth the risk -- but the zoom-rescan pass already only
        # runs on crops the fast pass struggled with (missing/low-
        # confidence/blurry), a small fraction of total frames, which is
        # exactly where paying more for a better read is worth it.
        self.ocr_precise = PaddleOCR(
            use_textline_orientation=True,
            text_detection_model_name="PP-OCRv5_server_det",
            text_recognition_model_name="PP-OCRv5_server_rec",
            enable_mkldnn=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
        )

    # ---------------------------------------------------------------
    def _preprocess_plate(self, crop):
        """Upscale a small plate crop; otherwise hand PaddleOCR the crop as-is.

        Previously this also ran grayscale -> bilateral filter -> CLAHE ->
        sharpen -> adaptive-threshold binarization here. Confirmed via
        direct debug instrumentation (dumping PaddleOCR's raw result) that
        this pipeline made PP-OCRv6's text-DETECTION stage return zero
        regions (`dt_polys: []`) even on clear, well-lit, in-focus crops a
        human reads immediately — no exception, no warning, just a
        structurally valid empty result, which is why it never showed up
        as an error anywhere. PP-OCRv6 is trained on natural images; full
        binarization destroys the gradient/edge information its detector
        relies on to find text at all. Removing it restored correct
        detection and reading immediately across every re-tested photo,
        including a gold-standard close-up that had regressed to reading
        nothing despite the plate detector finding a tight 79-85%-confidence
        box around the plate every time.
        """
        if crop is None or crop.size == 0:
            return None

        h, w = crop.shape[:2]

        # License plates need decent resolution — upscale small crops.
        target_height = 120
        if h < target_height:
            scale = target_height / h
            new_w = int(w * scale)
            crop = cv2.resize(crop, (new_w, target_height), interpolation=cv2.INTER_CUBIC)

        return crop

    # ---------------------------------------------------------------
    @staticmethod
    def _clean_plate_text(text):
        """Normalize OCR output and reject obviously-wrong reads."""
        if not text:
            return None

        text = text.strip().replace(" ", "").replace("-", "").replace("_", "").upper()

        # A real plate is only ever A-Z/0-9 -- unlike the length-specific
        # format checks below (which intentionally skip non-standard
        # lengths to avoid rejecting BH-series/military/commercial
        # plates), this rule holds at EVERY length and every known
        # format, so it's safe to apply unconditionally. Confirmed
        # directly on real Sentinel Grid data: a garbled OCR read
        # containing a literal "⊙" symbol was passing straight through
        # (length 8, outside the 9/10/11 format-checked range).
        if not re.fullmatch(r"[A-Z0-9]+", text):
            return None

        # Plates are typically 4-15 characters; must contain a digit.
        if len(text) < 4 or len(text) > 15:
            return None
        if not any(c.isdigit() for c in text):
            return None

        # A read at a length the standard format could plausibly produce
        # must actually match that shape -- catches both a digit/letter
        # OCR confusion within a 9/10-length read AND a spurious extra
        # character making it 11 (see _LENGTH_GATED above -- 11 is
        # unconditionally rejected, since the pattern can never match
        # that length anyway). Other lengths (BH-series, military, short
        # commercial plates) intentionally skip this and fall through to
        # acceptance above.
        if len(text) in _LENGTH_GATED and not _STANDARD_PLATE_RE.match(text):
            corrected = _try_correct_plate(text)
            if corrected is None:
                return None
            if _OCR_DEBUG:
                print(f"[ocr-debug] corrected '{text}' -> '{corrected}' (lookalike-character fix)")
            text = corrected

        return text

    # ---------------------------------------------------------------
    def _apply_ocr(self, crop, precise: bool = False):
        """Run OCR on a plate crop and return the cleaned plate text (or None).

        Indian plates are sometimes two-line (motorcycles especially: e.g.
        "GJ01" on one row, "FV7724" below it) — PaddleOCR returns each row
        as its own text fragment. Sort fragments top-to-bottom by their
        detection box and join them, rather than keeping only the first
        fragment, so a two-line plate reads as one string instead of
        silently losing every row but one.

        precise=True uses the slower, more accurate PP-OCRv5_server model
        (self.ocr_precise) instead of the routine PP-OCRv6_medium one --
        only the zoom-rescan pass sets this, not the per-frame default.
        """
        if crop is None or crop.size == 0:
            return None

        try:
            processed = self._preprocess_plate(crop)
            if processed is None:
                return None
            crop_dim = f"{processed.shape[1]}x{processed.shape[0]}"

            ocr_engine = self.ocr_precise if precise else self.ocr
            result = ocr_engine.ocr(processed)
            if not result or not result[0]:
                if _OCR_DEBUG:
                    print(f"[ocr-debug] crop={crop_dim} -> PaddleOCR returned no result at all")
                return None

            rec_texts = result[0].get("rec_texts")
            if not rec_texts:
                if _OCR_DEBUG:
                    dt_polys = result[0].get("dt_polys")
                    print(
                        f"[ocr-debug] crop={crop_dim} -> text DETECTOR found "
                        f"{len(dt_polys) if dt_polys is not None else 0} region(s), 0 recognized"
                    )
                return None

            rec_boxes = result[0].get("rec_boxes")
            if rec_boxes is not None and len(rec_boxes) == len(rec_texts):
                # box = [x1, y1, x2, y2] — sort by y1 (top edge) so multi-row
                # plates join in reading order regardless of the order
                # PaddleOCR happened to return them in.
                order = sorted(range(len(rec_texts)), key=lambda i: rec_boxes[i][1])
                combined = "".join(rec_texts[i] for i in order)
            else:
                combined = rec_texts[0]

            cleaned = self._clean_plate_text(combined)
            if _OCR_DEBUG and cleaned is None:
                print(f"[ocr-debug] crop={crop_dim} -> raw OCR text='{combined}' REJECTED by cleaning")
            return cleaned
        except Exception as e:
            print(f"[WARN] OCR failed: {e}")
            return None

    # ---------------------------------------------------------------
    def predict(self, frame, precise: bool = False):
        """
        Detect every plate in `frame` and OCR each one.

        precise=True uses the slower, more accurate OCR model for every
        detection found -- intended for the zoom-rescan pass (a small
        cropped/upscaled region, not a full frame), not the routine
        per-frame call.

        Returns:
            {
              "plate_no": str | None,   # text of the last/most confident plate (convenience field)
              "detections": [
                  {"bbox": (x1, y1, x2, y2), "confidence": float,
                   "class_name": "plate" | "military-plate", "plate_no": str | None},
                  ...
              ]
            }
        """
        if frame is None or frame.size == 0:
            return {"plate_no": None, "detections": []}

        results = self.yolo(frame, verbose=False)
        boxes = results[0].boxes
        names = results[0].names

        detections = []
        h, w = frame.shape[:2]

        for box in boxes:
            conf = float(box.conf[0])
            if conf < self.conf_threshold:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])

            # Padding scales with the box's own size, not a fixed pixel
            # count. A flat 8px margin is fine for a small/distant plate,
            # but for a large close-up plate an angled tilt can put real
            # plate content well outside a merely-8px-larger box, clipping
            # a corner before OCR ever sees it. Confirmed against a real
            # failure: an angled plate read as a 7-character fragment
            # missing both the leading state-code letters and part of the
            # trailing digits -- both ends cut, the signature of a
            # too-tight crop, not random OCR noise. 15% of the box's own
            # width/height (8px floor for tiny boxes) gives an angled
            # plate more room without dragging in excessive background
            # for a straight-on one.
            box_w, box_h = x2 - x1, y2 - y1
            pad_x, pad_y = max(8, int(0.15 * box_w)), max(8, int(0.15 * box_h))
            y1_pad, y2_pad = max(0, y1 - pad_y), min(h, y2 + pad_y)
            x1_pad, x2_pad = max(0, x1 - pad_x), min(w, x2 + pad_x)

            crop = frame[y1_pad:y2_pad, x1_pad:x2_pad]
            if crop.size == 0:
                continue

            plate_no = self._apply_ocr(crop, precise=precise)
            class_id = int(box.cls[0])

            detections.append({
                "bbox": (x1, y1, x2, y2),
                "confidence": conf,
                "class_name": names.get(class_id, str(class_id)),
                "plate_no": plate_no,
            })

        # Sort by confidence, highest first, so [0] is the best guess.
        detections.sort(key=lambda d: d["confidence"], reverse=True)
        best_plate = next((d["plate_no"] for d in detections if d["plate_no"]), None)

        return {"plate_no": best_plate, "detections": detections}
