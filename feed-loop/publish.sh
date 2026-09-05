#!/bin/sh
# Loops $SOURCE_FILE into MediaMTX via RTSP publish, simulating an always-on
# departmental camera feed. Waits (rather than crash-looping) if the file
# isn't there yet, since /media is user-supplied.
#
# Flags carried forward from the proven working config in the previous
# Model 2 build:
#   -rtsp_transport tcp   avoids the UDP "Broken pipe" drop seen over TCP-only
#                         Docker networking
#   -g 30 -keyint_min 30 -sc_threshold 0
#                         forces a 1s keyframe interval (at 30fps) — without
#                         this, x264 defaults to an ~8s GOP and HLS segments
#                         can't be shorter than that no matter what MediaMTX
#                         is configured for
#   -stream_loop -1       loop the source file forever

: "${SOURCE_FILE:?SOURCE_FILE env var required}"
: "${RTSP_URL:?RTSP_URL env var required}"

while [ ! -f "$SOURCE_FILE" ]; do
  echo "[feed-loop] Waiting for $SOURCE_FILE (mount it under ./media — see media/README.md)..."
  sleep 5
done

echo "[feed-loop] Publishing $SOURCE_FILE -> $RTSP_URL"
exec ffmpeg -re -stream_loop -1 -i "$SOURCE_FILE" \
  -c:v libx264 -preset veryfast -g 30 -keyint_min 30 -sc_threshold 0 \
  -an -f rtsp -rtsp_transport tcp "$RTSP_URL"
