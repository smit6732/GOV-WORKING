# Batch accuracy test data

Drop images and/or short video clips here to test the ANPR pipeline directly
(no live camera, no RTSP, no database — just the detection+OCR pipeline
itself) via `anpr_standalone/tools/batch_test.py`.

Supported: `.jpg` `.jpeg` `.png` `.bmp` for images, `.mp4` `.avi` `.mkv`
`.mov` for video clips.

Run (from the repo root, whole stack already up):

```bash
docker exec cctv_anpr python tools/batch_test.py /app/test_data
```

Prints a per-file table (events, vehicle detections, plate reads, timing)
and a total plate-read rate, plus every plate value actually read so you
can eyeball it against the real plate in each file.

Files here are gitignored — not part of the repo, same convention as
`media/`.
