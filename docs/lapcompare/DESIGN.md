# Lap Compare: design (cross-session comparison)

**Read this when:** building multi-session comparison, the session library, or anything that needs laps from different files to line up. The analysis features that sit on top are in `ANALYSIS-IDEAS.md`.

**Status:** v0 exists (one session at a time). Everything below "Target design" is **designed, not built**.

## v0, as built
`packages/lapcompare`: upload one session (`.rcz` or CSV), choose a part, overlay up to 8 laps, any signals against distance, delta time vs a reference lap, a combined wheel-speed plot, table view, and "Load slides" from a SlideFinder export.
- Lap data JSON (`GET /api/sessions/{id}/laps`): `{step, laps: [{n, source, time}], signals: [{key, unit, group}], values: {key: [per-lap arrays]}, time: [per-lap arrays], defaultLaps, session_id, session_start}`. `n` = display lap (restarts at 1 in the part), `source` = RaceChrono's lap number, `time` = lap time (s). Arrays are on a **distance grid of `step` metres measured from the start of each lap**; `time[i][j]` = seconds into lap `i` at grid point `j`.
- Slide markers: `POST /api/sessions/{id}/slides` with a SlideFinder CSV. Matched by `session_id`, else `session_start` (within 1 s), else (old exports) assumed to belong. Placed by `source_lap` and `time_in_lap_s`.
- Limits that motivate the design below: distance-from-lap-start does not line up across laps or sessions (GPS distance drifts; laps differ in length by tens of metres; the first lap starts at the pit exit, not the start/finish line), and each upload is forgotten.

## Target design

### Identity
- `session_id` = `racelog.Session.fingerprint` (12 hex chars: track name + first GPS timestamp rounded to the second; the same from CSV or `.rcz`; each part of an `.rcz` has its own). Known weakness: a recording starting within a few ms of a half-second boundary could get two ids across formats. When ingesting, treat sessions with the same track and `|t0 difference| < 1 s` as the same recording.
- Lap key = `(session_id, source_lap)`. Display numbers (1..N) only ever exist inside one view.

### Library: a saved cache of derived data
- Add a session once; it is read, aligned and stored; later comparisons never reread the 20 MB file. Location `~/.lapcompare/library/<session_id>/` with `meta.json` and the derived lap data.
- `meta.json`: source filename (informational), track name and gate hash, session start (UTC), part index, lap count, and **optional user tags**: car, driver, tires, conditions, notes. Tags make cross-day comparisons meaningful (different tires or temperature explain a time difference) and let the UI filter.
- The original file is **not copied and not required** once ingested. If the user deletes the `.rcz`, the library keeps working. Re-ingesting the same session (same `session_id`) replaces its entry.
- Storage format: undecided. Likely one `.npz` per session (arrays on the track grid) plus `meta.json`, with a small JSON index at the library root. Decide when building; keep it versioned (`format_version` in `meta.json`) so the derived data can be rebuilt after the alignment changes.

### Alignment: track position, not distance from lap start
Goal: any lap from any session at any point `s` along the track gives comparable values.
1. **Reference line** per track: the GPS path of one clean, complete lap (e.g. the best lap), smoothed, stored as a polyline with cumulative length. Kept per track (`~/.lapcompare/library/tracks/<track key>.json`) with the gate positions along it. Replace it when a better lap arrives; derived lap data records which reference version it used.
2. **Project** each lap's GPS points onto the reference polyline (nearest point, with continuity so it cannot jump between nearby straights). The result is **track position `s`** in metres. The start/finish gate is `s = 0`; checkpoint gates (`racelog.tracks`) give sector boundaries in `s`.
3. **Resample** every channel on a fixed `s` grid (about 2 m) per lap, plus the **time at each grid point**. Time at `s` is what makes delta-time between any two laps trivial: `delta(s) = t_A(s) - t_B(s)`.
4. **Lap boundaries and times from gate crossings** (`racelog.tracks.find_crossings`, interpolated between samples), not RaceChrono's lap markers, so laps from different sessions and formats are timed the same way. A lap is *complete* only if bounded by two start/finish crossings (out laps starting at the pit exit and in laps ending in the pits are not).
5. **Same-track check:** same track name and matching gate geometry (positions within a few metres). Refuse to mix different layouts. (Assumption, not yet confirmed with the user: different configurations of one circuit count as different tracks. The user has mentioned tracks they will use called laguna, west and east.)
- Validation oracle: on the sample `.rcz`, the sum of per-sector best times from gate crossings is 108.52 s, equal to the `optimalLaptime` RaceChrono stored (108.516 s), and the fastest lap equals `bestLaptime` (109.714 s). Keep a test that reproduces both.

### What the UI would add
Session picker (library list with tags), lap picker across sessions (colour by lap as today, label shows session + lap), the same signal and delta views on the `s` axis, sector boundaries drawn as vertical lines, and slide markers from SlideFinder exports for any session in the library.

### Suggested module layout when building
`racelog`: promote gate-crossing lap timing and per-sector times here (`racelog.timing`), since SlideFinder could use them too.
`lapcompare`: `library.py` (ingest, store, index), `align.py` (reference line, projection, resampling), `classify.py` (lap classes), `sectors.py` (sector statistics), `analysis/` (the ideas), `server.py` endpoints for the library, `web/` additions.

### Open decisions
- Storage format and how to version/rebuild derived data.
- How to pick and update the reference line (best lap vs median path); tracks recorded with different lines (e.g. a different pit exit) must not distort it.
- Library location and whether it can be moved or exported.
- Whether library comparisons also need a notion of "driver/car" beyond free-text tags.
- How to handle the first lap of a part (starts in the pits, joins mid-track) and the final in lap: treat as partial laps, usable only for the sectors they cover.
