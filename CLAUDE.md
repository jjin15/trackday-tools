# CLAUDE.md: index for working on this repo

Track-day tools for RaceChrono sessions. Three packages in `packages/`: `racelog` (library: reads sessions/tracks), `slidefinder` (finds slides, maps to video clips), `lapcompare` (compares laps). **Start with `docs/HANDOFF.md`** for current state and next steps.

## If you want to...
| Goal | Read |
|---|---|
| Know where things stand, what's verified, what's next | `docs/HANDOFF.md` |
| Know why something is the way it is | `docs/DECISIONS.md` |
| Find where code belongs / trace a file to a result | `docs/ARCHITECTURE.md` |
| Touch `.rcz` or CSV reading, units, channel numbers | `docs/racechrono-formats.md` |
| Change slide detection, presets, severity, output columns | `docs/slidefinder/NOTES.md` |
| Build cross-session comparison or the lap library | `docs/lapcompare/DESIGN.md` |
| Build the "where am I losing time" analysis | `docs/lapcompare/ANALYSIS-IDEAS.md` |

## Commands (repo root, venv at `.venv`)
```
.venv/bin/pip install -e packages/racelog -e "packages/slidefinder[dev]" -e "packages/lapcompare[dev]"
.venv/bin/python -m pytest                                  # all three packages (pytest.ini)
.venv/bin/python -m pytest packages/racelog                 # one package
SLIDEFINDER_GOLDEN_RCZ=<real .rcz> .venv/bin/python -m pytest   # also run the real-session .rcz vs CSV test
.venv/bin/slidefinder SESSION.rcz     |  .venv/bin/slidefinder serve   (:8765)
.venv/bin/lapcompare                  (:8766)
.venv/bin/python -m playwright install chromium             # once, for browser tests
```
No Node is installed. Python is 3.9 (`requires-python >= 3.9`; avoid newer syntax).

## Rules
- **Dependencies:** `slidefinder -> racelog`, `lapcompare -> racelog`. Apps never import each other; `racelog` imports neither. Apps talk through files (SlideFinder's export CSV carries `session_id`, `session_start`, `source_lap`).
- **SI units inside** (m/s, deg); convert to mph/km/h only at the edge.
- **Display laps restart at 1 within a part; `source_lap` is RaceChrono's own number.** Don't mix them.
- The user's real sessions are private: never commit them. The golden tests skip when files are absent.
- Prefer the `.rcz` as input; CSV exports work too. Both must give the same results (there is a test).

## Gotchas
- The CSV has **three `speed` columns** (gps, calc, canbus) and other duplicates. Pick by (name, source); use **GPS** speed (user's instruction).
- An `.rcz` stores CAN lateral/longitudinal acceleration in **m/s^2** (CSV shows G). It has **no calculated channels** (lean angle, combined G...).
- **Steering is ~5 Hz raw**; the CSV's smooth steering is interpolation. Short-duration thresholds (Loose preset) lean on 1-2 real samples.
- A session `.rcz` can hold **several parts** (stop/resume). Default is the part with the most laps. Lap numbers continue across parts.
- Reader errors should be readable (`RaceChronoFormatError`, `RczFormatError`, `TrackError`); the CLI turns them and `OSError` into one-line messages. Don't let tracebacks reach users.
- `Session.fingerprint` rounds the start to the second (CSV and `.rcz` start ~4 ms apart).
- Detection thresholds were tuned on **one** session. Don't tighten claims about accuracy without more data.

## Verification habits that paid off here
Compare the `.rcz` reader against the CSV on real data (not just synthetic); check results one-to-one by lap and time; install each package from a built wheel in a clean venv and run from outside the repo. When a check shows a surprising result, suspect the check first (twice a comparison script was wrong, not the code), then confirm.
