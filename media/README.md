# Mock departmental video feeds

Model 2's `feed-department-a` / `feed-department-b` containers loop these two
files into MediaMTX via RTSP, standing in for two real departmental VMS
systems (see `MODEL2_ARCHITECTURE.md`). Drop your own footage here:

- `media/department_a.mp4` — Camera `CAM-M2-001` (Home Department - Police, Ahmedabad)
- `media/department_b.mp4` — Camera `CAM-M2-002` (ACB, Surat)

Any h264-compatible mp4 works. Footage with a visible, readable vehicle
license plate lets you actually exercise the ANPR pipeline end-to-end
(tag a plate, watch a real alert fire). Files are gitignored — they're not
part of the repo; the `feed-loop` containers wait and retry until each file
appears.
