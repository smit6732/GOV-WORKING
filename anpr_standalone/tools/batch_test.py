#!/usr/bin/env python3
"""
Batch-tests the ANPR pipeline (vehicle detection + plate detection + OCR,
the exact same anpr.pipeline.ANPRPipeline used by the live service) against
a folder of local images and/or videos, and prints a per-file accuracy
table. No RTSP, no Kafka, no database -- runs the pipeline directly
in-process, so it's fast and has zero dependency on any camera being
reachable. Good for a controlled "how well does this actually read plates"
check, distinct from live-grid numbers which are also affected by real
network conditions and camera framing.

Run INSIDE the anpr container -- it already has every model/dependency
loaded, no separate setup needed:

    docker exec cctv_anpr python tools/batch_test.py /app/test_data

Drop test images (.jpg/.jpeg/.png/.bmp) and/or videos (.mp4/.avi/.mkv/.mov)
into the ./test_data folder on the host first (mounted into the container
at /app/test_data -- see test_data/README.md).
"""

import argparse
import os
import sys
import time

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from anpr.pipeline import ANPRPipeline  # noqa: E402

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov"}


def process_image(path):
    frame = cv2.imread(path)
    if frame is None:
        return None
    pipeline = ANPRPipeline(camera_id=os.path.basename(path))
    return pipeline.process_frame(frame, track=False)


def process_video(path, sample_every_n_frames):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    pipeline = ANPRPipeline(camera_id=os.path.basename(path))
    all_events = []
    frame_idx = 0
    frames_processed = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % sample_every_n_frames == 0:
            all_events.extend(pipeline.process_frame(frame, track=True))
            frames_processed += 1
        frame_idx += 1
    cap.release()
    return all_events, frames_processed, frame_idx


def summarize(fname, kind, events, extra=None):
    if events is None:
        return {"file": fname, "type": kind, "status": "FAILED TO OPEN"}
    vehicles = sum(1 for e in events if e.get("vehicle_bbox"))
    plate_reads = [e["plate_no"] for e in events if e.get("plate_no")]
    row = {
        "file": fname,
        "type": kind,
        "status": "ok",
        "events": len(events),
        "vehicles": vehicles,
        "plates_found": len(plate_reads),
        "plate_reads": plate_reads,
    }
    if extra:
        row.update(extra)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", help="Directory of test images/videos (e.g. /app/test_data)")
    parser.add_argument(
        "--video-sample-every", type=int, default=15,
        help="Process every Nth video frame (default 15 -- roughly 2fps on a 30fps clip)",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.folder):
        sys.exit(f"Not a directory: {args.folder}")

    files = sorted(
        f for f in os.listdir(args.folder)
        if os.path.splitext(f)[1].lower() in IMAGE_EXTS | VIDEO_EXTS
    )
    if not files:
        sys.exit(
            f"No image/video files found in {args.folder} "
            f"(looked for {sorted(IMAGE_EXTS | VIDEO_EXTS)})"
        )

    print(f"[batch-test] found {len(files)} file(s) in {args.folder}\n")

    results = []
    for fname in files:
        path = os.path.join(args.folder, fname)
        ext = os.path.splitext(fname)[1].lower()
        start = time.time()

        if ext in IMAGE_EXTS:
            events = process_image(path)
            row = summarize(fname, "image", events)
        else:
            out = process_video(path, args.video_sample_every)
            if out is None:
                row = summarize(fname, "video", None)
            else:
                events, frames_processed, total_frames = out
                row = summarize(
                    fname, "video", events,
                    extra={"frames_processed": frames_processed, "total_frames": total_frames},
                )

        row["elapsed_s"] = round(time.time() - start, 2)
        results.append(row)
        print(f"[batch-test] {fname}: {row['status']} ({row['elapsed_s']}s)")

    # ---- table ----
    print("\n" + "=" * 104)
    print(f"{'File':<28} {'Type':<6} {'Events':<8} {'Vehicles':<9} {'Plates Read':<12} {'Time(s)':<8}")
    print("-" * 104)
    total_events = total_vehicles = total_plates = 0
    for r in results:
        if r["status"] != "ok":
            print(f"{r['file']:<28} {r['type']:<6} {'--':<8} {'--':<9} {'FAILED':<12} {'--':<8}")
            continue
        print(
            f"{r['file']:<28} {r['type']:<6} {r['events']:<8} {r['vehicles']:<9} "
            f"{r['plates_found']:<12} {r['elapsed_s']:<8}"
        )
        total_events += r["events"]
        total_vehicles += r["vehicles"]
        total_plates += r["plates_found"]
    print("=" * 104)
    print(f"TOTAL: {total_events} events, {total_vehicles} vehicle detections, {total_plates} plate reads")
    if total_vehicles:
        print(f"Plate-read rate (plate reads / vehicle detections): {100 * total_plates / total_vehicles:.1f}%")

    plate_rows = [r for r in results if r.get("plate_reads")]
    if plate_rows:
        print("\nPlate values read per file (check these by eye against the real plate):")
        for r in plate_rows:
            print(f"  {r['file']}: {r['plate_reads']}")


if __name__ == "__main__":
    main()
