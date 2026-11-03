# SlideFinder notes

**Read this when:** changing how slides are detected, scored or presented; tuning presets; or explaining a result.

## What it does
Reads a session, finds slides, ranks them, and says for each: lap, sector, where in the video (clip N at mm:ss). Output is a ranked table (CLI `slides.csv`, web page) so the user can pull clips from GoPro footage that is **not synced** with the data.

## Pipeline
1. `racelog.loader.load_session` -> `Session` (50 Hz). `.rcz` default part = the one with the most laps.
2. `racelog.start.detect_start`: time zero = when driving on track begins. First point where GPS speed stays >= 20 m/s for 2 s, then back up to the last moment it was below 5 m/s (the pit-exit launch). On the sample session: 02:59.23 into the data (RaceChrono's own lap 1 starts 1.8 s earlier at 02:57.45; override with `--start-time`).
3. `detect.auto.detect` picks a detector and returns runs plus a one-line note shown to the user.
4. `report.build_events` turns runs into rows: lap, sector (via `racelog.tracks.find_crossings`), `time_in_lap_s`, times from time zero, video clip (`sync.locate_clip`), wall clock, peaks, severity, identifiers.
5. `report.rank_events` sorts by severity and adds `rank`.

## Detector 1: opposite lock (needs a steering angle)
`detect/steering.py`. A slide = steering one way while the car rotates the other, sustained. Quick counter-steers that *cancel* a slide are not slides, so the mismatch must hold.
- Smooth steering and yaw (0.2 s). Calibrate sign and scale by regressing yaw on steering at speed >= `min_speed` (sign is not assumed; sample: +, 0.252 deg/s per degree).
- Mask = speed >= `min_speed` AND |steer| >= `min_steer` AND |yaw| >= `min_yaw` AND sign(steer) != sign(yaw). Merge runs closer than `merge_gap` (0.5 s). Keep runs >= `min_duration`.
- **Yaw** is gyro z (deg/s), used because it is far less noisy than differencing GPS bearing. The user first proposed "steering vs GPS turn direction"; yaw is the same idea.
- **Severity** = duration (s) x mean |yaw| (deg/s) over the slide, i.e. roughly "degrees of rotation while opposed". It only ranks slides within a session. It says nothing about speed, danger, or slip angle, and ignores how much steering was used.

## Detector 2: slip angle (no steering angle logged)
`detect/slip.py`. Slip = where the car points minus where it is going.
- Yaw = gyro projected onto gravity (the logger was ~6 degrees off vertical), integrated to a heading. GPS course is the direction of travel. Sign (which way the gyro counts) is found from the correlation between course rate and yaw above 15 m/s.
- Integration drifts, so heading is re-anchored to GPS course on **straights** (|yaw| < 3 deg/s, speed > 15 m/s, for 1 s), interpolating the offset between anchors. Slip = wrap(course - heading - offset), smoothed 0.2 s.
- Mask = |slip| >= `min_slip` AND speed >= `min_speed`; merge and minimum duration as above.
- **Known blind spot:** a slip held steady on a straight with almost no yaw looks like a straight, so it gets re-anchored and under-reported. Slides in corners, where the car keeps rotating, are fine. Rejecting anchors whose offset jumps (tried at 4-14 degrees) made agreement with the steering detector *worse* on real data, so it was dropped. Do not retry without a better idea.
- It finds a **different, usually smaller** set of slides than detector 1. Tell users so (the UI note does).

## Presets (the main control; numeric thresholds are the Advanced panel)
| Preset | steering: duration / steer / yaw | slip: angle / duration | Sample session (19 laps): steering / slip |
|---|---|---|---|
| Strict (default) | 0.75 s / 20 deg / 10 deg/s | 12 deg / 0.75 s | 21 / 14 |
| Balanced | 0.5 s / 15 deg / 8 deg/s | 11 deg / 0.5 s | 31 / 28 |
| Loose | 0.3 s / 10 deg / 5 deg/s | 10 deg / 0.4 s | 40 / 39 |
`min_speed` 10 m/s (22 mph) everywhere. Duration was the biggest lever, then steering, then yaw. Chosen by sweeping on one session, **not** validated against footage: the extra Balanced/Loose slides are unverified.

**Agreement between the detectors on the sample** (a run counts as matched if it overlaps one from the other): Strict 10 of 14 slip runs match a steering slide, and slip finds 10 of 21 steering slides; Balanced 19/28 and 19/31; Loose 24/39 and 24/40. Roughly: slip finds about half to two thirds of what opposite lock finds, and most of what it flags is also an opposite-lock slide.

## Sample-session facts worth remembering
- 21 slides at Strict. Biggest: lap 14, T6->T7, 5.0 s, severity ~145; second: lap 13, T6->T7, 3.4 s. Eight of the 21 are in sector T6->T7, five in T11->T1-2, three in T10->T11.
- The morning part (laps 1-7) has **0 slides** at Strict: steering and yaw are healthy (checked) and it has only 0.7 s of raw opposite lock against 42 s in the afternoon. The steering-to-yaw scale differs between parts (0.448 vs 0.252) because it depends on speed and driving, not logger mounting (tilt was 6.9 vs 5.5 degrees).
- Steering is logged at ~5 Hz. The CSV's smooth steering is RaceChrono's interpolation. At 0.2 s smoothing and a 0.3 s Loose minimum, Loose rests on about 1-2 real steering samples; trust Strict more.

## Video mapping
`sync.locate_clip(video_t, clip_lengths)`: clips are assumed back to back; the last length repeats. `video_t = session_time + offset`. Default clip length 12:48 (GoPro chapter). `sync.solve_offset` turns "slide X is at clip N, mm:ss" into the offset. Error accumulates if real chapters differ from the stated lengths (give a list: `12:48,12:47,05:10`). There is no GoPro telemetry parsing and no ffmpeg; this was a deliberate scope choice.

## Output columns (CLI `slides.csv` = web Export)
`rank, lap, [sector, sector_name,] time_in_lap_s, session_time, session_time_s, video_time, [clip, clip_time,] wall_clock_utc, duration_s, peak_steer_deg, peak_yaw_dps` (or `peak_slip_deg`), `min_speed_mph, lat, lon, severity, session_id, session_start, source_lap`.
`lap` is the display number (restarts at 1 in the part); `source_lap` is RaceChrono's. `session_id`/`session_start` identify the recording so Lap Compare can place the slide on the right lap. The golden file `tests/local/golden_slides.csv` predates the last three columns; its test compares only the original ones.

## CLI and web
`slidefinder FILE [--sensitivity strict|balanced|loose] [--part N] [--offset S] [--clip-length 12:48[,..]] [--track NAME|PATH|none] [--sort severity|time] [--top N]` plus Advanced flags (`--method`, `--min-slip/-speed/-steer/-yaw/-duration`, `--merge-gap`, `--start-time`, `--no-trim`, `--pit-speed`, `--keep-lap-numbers`, `--hz`). `slidefinder serve [--port 8765] [--no-open]` runs the web app.
Web API (all JSON): `GET /api/config`, `POST /api/sessions` (upload), `GET|DELETE /api/sessions/{id}`, `POST .../part/{n}`, `POST .../track` (add a track .rcz), `GET .../slides?preset=&min_duration=&...&offset=&clip_lengths=&t_start=`, `POST /api/sync/solve`. Slide `id` = `round(session_time_s + t_zero, 2)` so "not a slide" choices (kept in the browser's localStorage) survive offset changes.

## Tuning history (so it isn't redone)
- Counter-steer filtering by duration, not by magnitude: simplest rule that matched the user's description.
- GPS speed, not CAN speed, everywhere (user instruction). The CSV has three `speed` columns; pick (speed, gps).
- Severity is only a ranking; resist turning it into a "danger" score.
- Strict was kept as the default so a first run has few false positives (user's request).
