# Decisions

**Read this when:** tempted to change something that was a deliberate choice. Newest last. Each entry: what, why, and what would change the answer.

### 2026-10-30 Detect slides as opposite lock, using gyro yaw
Compare steering direction with the car's actual rotation; a quick counter-steer that cancels a slide is not a drift, so the mismatch must be sustained. Yaw (gyro z) stands in for "the direction of the turn" because it is far less noisy than GPS bearing. *Why:* it is the user's own definition; yaw is the same idea with cleaner data. *Revisit if:* users' cars have no steering channel (done: see the slip fallback).

### 2026-10-30 Strict defaults first
Min speed 10 m/s, steering >= 20 deg, opposite rotation >= 10 deg/s, held >= 0.75 s. *Why:* the user asked for few false positives to start. Looser settings exist as presets.

### 2026-10-30 Use GPS speed, not CAN speed
*Why:* user instruction. The CSV has three `speed` columns; always select (speed, gps).

### 2026-10-31 Time zero is when driving on track starts, not when logging started
Detected from GPS speed (>= 20 m/s for 2 s, back to the last time under 5 m/s). *Why:* the user starts the session long before driving, and the video starts later. Override with `--start-time`; disable with `--no-trim`.

### 2026-10-30/31 Lap numbers restart at 1; keep RaceChrono's as `source_lap`
*Why:* the user's file started at lap 8 and found that confusing. The original is kept because it is the only number that is stable across files, and the slide export needs it.

### 2026-10-31 Output ranked by severity; severity = duration x mean |yaw|
*Why:* so the user can "just pick the best ones". It is a ranking, not a measure of danger.

### 2026-10-31 Video: manual offset, clip lengths, one-slide solver; no GoPro parsing, no ffmpeg
*Why:* user scope choice; keeps the tool dependency-free. Default clip length 12:48. *Revisit if:* the user wants auto-sync (GoPro GPS telemetry) or clip cutting.

### 2026-11-03 Make it a local web app with presets, not a flag-heavy CLI
Sensitivity presets (Strict/Balanced/Loose) as the main control, a collapsed Advanced panel with plain-language labels, a "not a slide" button instead of tuning. Runs on the user's machine so session data stays private. *Why:* the aim is a tool others can use; many numeric flags are not usable.

### 2026-11-03 Add a no-steering detector (slip angle)
*Why:* many cars/loggers have no steering channel. *Cost:* finds a different, smaller set; documented and noted in the UI. Rejecting straight-line anchors to fix its blind spot was tried and made agreement worse; reverted.

### 2026-11-03 Preset values chosen by sweeping one session
Not validated against footage. Loose rests on ~1-2 real steering samples because steering is ~5 Hz.

### 2026-11-03 Read `.rcz` directly; it is the preferred input
*Why:* ~12x smaller, ~9x faster, carries the track, and loses nothing (CSV = RaceChrono's interpolation of the same data). A multi-part `.rcz` defaults to the part with the most laps; the user can choose. The format was reverse-engineered from one file; see `racechrono-formats.md`.

### 2026-11-03 Split into three packages: `racelog`, `slidefinder`, `lapcompare`
One repo, separate `pyproject.toml` and CLI each; apps depend only on `racelog`, never on each other. *Why:* the user wants the lap comparison as its own app, able to grow into a cross-session analysis tool, with shared import code. Rejected: one package with two apps (installing either pulls in the other); separate repos (too much overhead while the shared code is still moving).

### 2026-11-03 SlideFinder loses its lap tab; Lap Compare loads SlideFinder's export
SlideFinder's CSV carries `session_id`, `session_start`, `source_lap`; Lap Compare matches slides to laps with them. *Why:* keeps the apps independent.

### 2026-11-03 Lap Compare will use a saved library of derived, track-aligned lap data
Laps keyed by session + source lap; original files not required after ingest; alignment by track position on a reference line, lap times from gate crossings. *Why:* cross-session comparison needs alignment that distance-from-lap-start cannot give, and re-reading 20 MB files is slow. **Designed only**: `docs/lapcompare/DESIGN.md`.

### 2026-11-03 Library name `racelog`
Working name; easy to change (package dir, imports, three `pyproject.toml` files).
