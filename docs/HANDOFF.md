# Handoff: where things stand

**Read this first when resuming.** Last updated 2026-11-03. Then `CLAUDE.md` (commands, gotchas), `DECISIONS.md` (why), and the doc for whatever you are about to touch.

## What exists
Three packages in one repo (`packages/`): **`racelog`** (reads RaceChrono `.rcz` and CSV, tracks, sessions), **`slidefinder`** (finds slides, ranks them, maps to GoPro clips; CLI + web on :8765), **`lapcompare`** (overlays laps; CLI + web on :8766). Apps depend on `racelog` only. Layout and data flow: `ARCHITECTURE.md`.

SlideFinder is done for its scope. Lap Compare is **v0**: one session at a time, one signal viewer, plus loading SlideFinder's slides as markers. The cross-session library and all analysis are **designed but not built** (`docs/lapcompare/DESIGN.md`, `docs/lapcompare/ANALYSIS-IDEAS.md`).

## Verified (2026-11-03)
- `pytest` from the repo root: **106 passed** with `SLIDEFINDER_GOLDEN_RCZ` set (racelog 23, slidefinder 64, lapcompare 19); 105 passed + 1 skipped without it. Browser tests ran (Playwright + Chromium).
- Real session (CSV and `.rcz` of the same recording): **21 slides** at Strict, identical to the golden file on lap, sector, clip and start time; the `.rcz` and CSV agree one-to-one (start times within 0.02 s).
- Each app installs alone from a built wheel with `racelog` (SlideFinder env has no `lapcompare`/`plotly`; Lap Compare env has no `slidefinder`) and runs from a directory outside the repo: CLI on the real `.rcz`, `serve` pages and static files, upload, slides, lap data.
- Lap Compare loads SlideFinder's real export and marks **21 of 21** slides on the right laps, from both the `.rcz` export and the CSV export (the two give the same `session_id`); against a different recording it marks 0 and says so.
- Real-browser run of both pages with the real `.rcz`: no JavaScript errors; SlideFinder has no tabs or View buttons; slide markers land on the speed dips.
- The sector prototype's numbers (`docs/lapcompare/ANALYSIS-IDEAS.md`) reproduce from its appendix script, including the sum of best sectors = 108.516 s = RaceChrono's stored `optimalLaptime`.

## Not verified / known weak spots
- **One session, one car.** The `.rcz` layout and the CAN channel-number table come from a single archive (RaceChrono 10.2.4, CAN-bus car). Other cars/versions may not read fully. Errors say what is missing. Needs more sample files.
- **Preset values are not validated against footage.** Strict is the trusted setting; Balanced/Loose extras are unverified. Steering is ~5 Hz, so Loose rests on 1-2 real samples.
- **The no-steering detector** matches the steering detector only partly (Strict: 10 of its 14 runs match). Documented in `slidefinder/NOTES.md`. It has a known blind spot.
- **Clip mapping assumes** back-to-back clips of the stated lengths (default 12:48); real GoPro chapters can differ.
- **Fingerprint edge case:** a recording starting within a few ms of a half-second boundary could get two ids across formats (`racechrono-formats.md`).
- Front-end code is duplicated between the two web apps (colour tokens, drop zone, part menu).
- No `LICENSE` file yet (the user's call).

## Where the user's data is
- Real CSV: a `session_*.csv` in the repo root (git-ignored; never commit it).
- Real `.rcz`: kept outside the repo (NOT committed); point `SLIDEFINDER_GOLDEN_RCZ` at it. Two parts: laps 1-7 (morning, 0 slides at Strict) and laps 8-26 (afternoon, the CSV's content).
- Golden results: `packages/slidefinder/tests/local/golden_slides.csv` (git-ignored). The golden tests find the CSV in the repo root and need `SLIDEFINDER_GOLDEN_RCZ=<path to the .rcz>` for the `.rcz` comparison (or a `session_*.rcz` in the repo root).
- **Stale files in the repo root** from the pre-split scripts: `slides.csv`, `laps.html`. Safe to delete; they are git-ignored and nothing reads them.

## Resume checklist
```
cd <path to this repo>
.venv/bin/pip install -e packages/racelog -e "packages/slidefinder[dev]" -e "packages/lapcompare[dev]"   # if the venv is gone
SLIDEFINDER_GOLDEN_RCZ=/path/to/session.rcz .venv/bin/python -m pytest
.venv/bin/slidefinder serve        # :8765        .venv/bin/lapcompare     # :8766
```
Browser tests need `.venv/bin/python -m playwright install chromium` once.

## Suggested next steps (in order)
1. **Single-session analysis in Lap Compare** (no library needed): promote gate-crossing lap timing and per-sector times into `racelog`, add lap classification and a sector table (best, median, std, median-best) to the UI. Delivers the user's inconsistency / time-left / largest-improvement ideas for one session. See `docs/lapcompare/ANALYSIS-IDEAS.md` "First steps".
2. **Track-position alignment and the library** (`docs/lapcompare/DESIGN.md`) so laps from different sessions can be compared.
3. **Corners and grip utilization** (needs a combined-G computation in `racelog`; `.rcz` has no calculated channels).
4. More sample files from other cars/loggers to harden the readers.
5. Optional: validate the presets against footage; GoPro auto-sync was declined for now.

## Questions to put to the user when resuming
- Is a different configuration of the same circuit a different track? (Assumed yes.)
- Clean-lap threshold: keep 1.5 s? (Only 7 of 18 laps pass on the sample session.)
- Where should the library live, and should it be exportable?
