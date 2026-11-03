# Track day tools for RaceChrono

Tools for going through a track day after the fact, using the sessions you log with [RaceChrono](https://racechrono.com). Everything runs on your own computer; your data never leaves it.

- **SlideFinder** finds the slides (drifts) in a session and tells you which video clip, and how far into it, to look at. It is for the case where your GoPro footage is not synced with your data and you want to pull clips without scrubbing through hours of video.
- **Lap Compare** overlays laps from a session and compares any logged signal (speed, throttle, brake, steering, and so on) against distance.
- **racelog** is the library underneath both. It reads RaceChrono sessions and track files.

| Package | What it is | Run it |
|---|---|---|
| [`slidefinder`](packages/slidefinder/README.md) | Finds slides, ranks them, maps them to video clips | `slidefinder serve` |
| [`lapcompare`](packages/lapcompare/README.md) | Compares laps | `lapcompare` |
| [`racelog`](packages/racelog/README.md) | Reads `.rcz` archives, CSV exports and track files | imported by the apps |

The apps depend on `racelog` and never on each other.

## Install

You need Python 3.9 or newer. From this folder:

```
python3 -m venv .venv
.venv/bin/pip install -e packages/racelog -e packages/slidefinder -e packages/lapcompare
```

## Run

**SlideFinder**

```
.venv/bin/slidefinder serve
```

A page opens at http://127.0.0.1:8765. Drop your session file on it. You get the slides, biggest first, each with its lap, sector and "Clip 3 at 00:06". Choose Strict, Balanced or Loose to change how many it finds, enter how long your video files are, and use *Line up with my video* to correct the offset once you have found one slide in your footage. *Export CSV* saves the list.

It also works from the command line:

```
.venv/bin/slidefinder ~/path/to/session.rcz --top 10
```

This prints a ranked table and writes `slides.csv`. `slidefinder --help` lists every option.

**Lap Compare**

```
.venv/bin/lapcompare
```

A page opens at http://127.0.0.1:8766. Drop a session on it, pick laps and signals. *Load slides* reads the CSV exported from SlideFinder and marks each slide on its lap.

Stop either one with Ctrl+C in the terminal.

## Your files

- Use the **session file (`.rcz`)** RaceChrono saves. It is about a tenth the size of a CSV export and carries the track, so sectors work with no extra file. CSV exports (format 3) work too.
- A session that you stopped and resumed holds several *parts*. The one with the most laps is used by default; a *Part* menu (or `--part N`) picks another.
- Sectors come from the track's checkpoints. Sonoma is included; add another circuit's track file from the page, or with `--track path/to/track.rcz`.

## Status

- **SlideFinder:** working. Tested on one real session (a car with a steering-angle channel). Without a steering channel it falls back to a different detector that finds a smaller set of slides.
- **Lap Compare:** a first version. One session at a time. Comparing laps across sessions and analysing where time is lost (inconsistent corners, time left on the table, grip use) are designed but not built.
- Only one session from one car has been tried. Other cars or logger setups may not read fully; the error message says what is missing.
- Video mapping assumes your clips run back to back at the length you give. There is no automatic video sync.

## Development

```
.venv/bin/pip install -e packages/racelog -e "packages/slidefinder[dev]" -e "packages/lapcompare[dev]"
.venv/bin/python -m pytest
```

The browser tests need Chromium for Playwright (`.venv/bin/python -m playwright install chromium`) and are skipped without it. A few tests compare against a private real session and are skipped if it isn't present.

[`CLAUDE.md`](CLAUDE.md) is the index for anyone (or any assistant) picking the project up, and [`docs/HANDOFF.md`](docs/HANDOFF.md) says where things stand and what to do next.

## License

[MIT](LICENSE).
