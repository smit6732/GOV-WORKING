"""
Run the ANPR pipeline continuously on a video file, webcam, or RTSP
stream, with vehicle tracking enabled, printing one JSON event per
line to stdout (and appending to anpr_events.jsonl).

Usage:
    python examples/process_video_stream.py 0                       # webcam
    python examples/process_video_stream.py path/to/video.mp4
    python examples/process_video_stream.py rtsp://user:pass@host/stream1
"""

import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from anpr.pipeline import ANPRPipeline  # noqa: E402
from service.sinks import ConsoleSink, JSONLFileSink, MultiSink  # noqa: E402

TARGET_FPS = 2.0  # ANPR doesn't need every frame — throttle to save CPU


def main():
    if len(sys.argv) < 2:
        print("Usage: python examples/process_video_stream.py <0|path|rtsp-url>")
        sys.exit(1)

    source = sys.argv[1]
    src = int(source) if source.isdigit() else source

    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        print(f"Could not open source: {source}")
        sys.exit(1)

    pipeline = ANPRPipeline(camera_id="demo-stream")
    sink = MultiSink(ConsoleSink(), JSONLFileSink("anpr_events.jsonl"))

    interval = 1.0 / TARGET_FPS
    last = 0.0
    print(f"Streaming from {source} — Ctrl+C to stop.\n")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Stream ended or frame not received.")
                break

            now = time.time()
            if now - last < interval:
                continue
            last = now

            for event in pipeline.process_frame(frame, track=True):
                sink.emit(event)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        cap.release()


if __name__ == "__main__":
    main()
