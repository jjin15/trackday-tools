# Architecture

**Read this when:** deciding where code belongs, adding a package, or tracing how a file becomes a result.

## Packages
```
packages/
  racelog/       library: read sessions and tracks. Knows nothing about slides or lap comparison.
  slidefinder/   app: detect slides, rank them, map to video clips.   CLI `slidefinder`   web :8765
  lapcompare/    app: overlay and compare laps.                        CLI `lapcompare`    web :8766
docs/  CLAUDE.md  README.md  pytest.ini
```
**Dependency rule:** `slidefinder -> racelog` and `lapcompare -> racelog` only. Neither app imports the other; `racelog` imports neither. Checked with a grep in the verification step (see HANDOFF). Apps talk to each other only through files: SlideFinder's exported CSV carries `session_id`, `session_start` and `source_lap`, which Lap Compare reads to mark slides.

Dev setup is one venv at the repo root with all three installed editable; `pytest` from the root runs everything (`pytest.ini` uses importlib import mode so test files can share names).

## Data flow
```
.rcz or CSV --loader--> Session (50 Hz frame) --detect--> [Run] --report--> events table --> CLI csv / web
                          |                                                    ^
            tracks (gates, sectors) ------------- find_crossings / sector_at --+
            start.detect_start -------------------- time zero ------------------+
            sync.locate_clip ---------------------- video clip + time ----------+
.rcz/CSV --laps.build_data--> per-lap signals by distance --> Lap Compare web
```

## racelog (`packages/racelog/src/racelog/`)
| Module | Role |
|---|---|
| `session.py` | `Session`: `df`, `t0` (unix s), `hz`, `meta`. `fingerprint` = short id of a recording (track + start second), the same from CSV or `.rcz`. |
| `racechrono.py` | CSV: `read_header`, `Header.find(name, source)`, `load_session`. Errors: `RaceChronoFormatError`. |
| `rcz.py` | `.rcz`: `list_parts`, `Channels` (raw arrays), `load_session`, `CAN_CHANNELS`, `interp`. Errors: `RczFormatError`. |
| `loader.py` | One entry point for both formats: `load_session`, `list_parts`, `default_part`, `embedded_track`, `track_name`, `FormatError` tuple. |
| `tracks.py` | `.rcz` track files: `load_gates`, registry (`list_tracks`, `match_session_track`, `find_track`), `add_user_track`, `find_crossings`, `sector_at`. |
| `turns.py` | Turn maps (`data/turns/*.json`, user's in `~/.racelog/turns`): `find_turns(track_name)`, `TurnMap.labels(lat, lon)` -> "T7" / "after T7", `build_turn_map` to make one. SlideFinder's `turn` column comes from here. |
| `start.py` | `detect_start`: when the car leaves the pits and starts driving on track. |
| `util.py` | `fmt_time`. |
| `testing.py` | Synthetic sessions and `.rcz`/CSV writers for tests in any package. Not part of the reading API. |
| `data/tracks/` | Bundled track files (Sonoma). |

**`Session.df` columns:** `t` (s from first sample), `lap_number` (RaceChrono's; NaN between laps), `latitude`, `longitude`, `speed` (GPS, m/s), `steer` (deg, NaN if not logged), `yaw` (gyro z, deg/s), `bearing` (GPS course, deg), `ax ay az` (G), `gx gy gz` (deg/s). Missing channels are all-NaN, never absent.
**Conventions:** SI internally (m/s, deg); convert to mph/km/h only at the edge (CLI table, web, lap-viewer signals). Display lap numbers restart at 1 within the chosen part; RaceChrono's own number is kept as `source_lap`. Times in results are measured from `t_zero` (the detected on-track start).

## slidefinder (`packages/slidefinder/src/slidefinder/`)
`detect/steering.py` (opposite lock), `detect/slip.py` (no-steering fallback), `detect/auto.py` (chooses, returns `Detection` with a human note), `presets.py` (Strict/Balanced/Loose + Advanced-panel metadata), `report.py` (`build_events`, `rank_events`), `sync.py` (clip lengths -> clip + time; offset solver), `cli.py`, `server.py` + `web/`. Details: `docs/slidefinder/NOTES.md`.

## lapcompare (`packages/lapcompare/src/lapcompare/`)
v0: `laps.py` (lap-by-distance data from CSV or `.rcz`), `server.py` (upload, part, laps, slide-marker matching), `cli.py`, `web/` (`laps.js` is the viewer, `app.js` the page). Design for what comes next: `docs/lapcompare/`.

## Servers
Both are single-process FastAPI apps on 127.0.0.1. Uploads are streamed to a temp directory that is deleted on shutdown (FastAPI lifespan); parsed sessions live in memory keyed by a short id and are lost on restart (the page reopens a session from `#session=<id>` only while the server is alive). Nothing is stored in the repo or sent anywhere.

## User data on disk
`~/.racelog/tracks/` tracks the user added (the old `~/.slidefinder/tracks/` is still read). Planned: `~/.lapcompare/library/` (see `docs/lapcompare/DESIGN.md`). The session files themselves live wherever the user keeps them; the repo's `.gitignore` excludes `session_*.csv`, `slides.csv`, `laps.html` and `tests/local/`.

## Tests
Synthetic data (`racelog.testing`) for logic and for the loaders/servers/browser pages, plus **golden tests** against the user's real session (skipped if absent): `packages/slidefinder/tests/test_golden.py` (the 21 slides; `.rcz` equals CSV) and `tests/local/golden_slides.csv`. Browser tests use Playwright + Chromium and skip without it.

## Known duplication
The two web apps share colour tokens, the drop zone and the part menu by copy. If a third front end appears, extract a shared static bundle.
