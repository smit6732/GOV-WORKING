"""
Run the ANPR pipeline on a single image and save an annotated copy.

Usage:
    python examples/process_image.py path/to/image.jpg
"""

import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from anpr.pipeline import ANPRPipeline  # noqa: E402


def draw_events(frame, events):
    for e in events:
        if e["vehicle_bbox"]:
            x1, y1, x2, y2 = e["vehicle_bbox"]
            label = e["vehicle_class"] or "vehicle"
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 128, 0), 2)
            cv2.putText(frame, label, (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 128, 0), 2)

        if e["plate_bbox"]:
            x1, y1, x2, y2 = e["plate_bbox"]
            label = e["plate_no"] or "?"
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, label, (x1, y2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    return frame


def main():
    if len(sys.argv) < 2:
        print("Usage: python examples/process_image.py path/to/image.jpg")
        sys.exit(1)

    image_path = sys.argv[1]
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"Could not read image: {image_path}")
        sys.exit(1)

    pipeline = ANPRPipeline(camera_id="demo-image")
    events = pipeline.process_frame(frame)

    print(json.dumps(events, indent=2, default=str))

    annotated = draw_events(frame.copy(), events)
    out_path = str(Path(image_path).with_suffix("")) + "_annotated.jpg"
    cv2.imwrite(out_path, annotated)
    print(f"\nAnnotated image saved to: {out_path}")


if __name__ == "__main__":
    main()
