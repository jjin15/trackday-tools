# SlideFinder

Find the slides in a [RaceChrono](https://racechrono.com) session so you can pull the right clips from your GoPro footage, without scrubbing through it by hand.

Give it a RaceChrono session file (`.rcz`, or a CSV export). It lists every slide, ranked biggest first, with the lap, the sector, and **which video file and how far into it** to look. It also overlays your laps against distance so you can compare lines, speed and pedal traces.

Everything runs on your own computer. Your session never leaves it.

## Install

You need Python 3.9 or newer.

From the repository root (SlideFinder uses the shared `racelog` package next to it):

```
python3 -m venv .venv
.venv/bin/pip install packages/racelog packages/slidefinder
```

## Use it

### The web app (easiest)

```
.venv/bin/slidefinder serve
```

A page opens in your browser. Drop your RaceChrono session on it.

1. **Pick a sensitivity.** *Strict* only reports obvious, sustained slides. *Balanced* and *Loose* catch smaller ones, with more false alarms. The count updates as you switch. Open **Advanced** to adjust the individual thresholds.
2. **Tell it how long your video files are.** GoPro splits recordings into chapters; the default is 12:48 each. Use a list like `12:48,12:47,05:10` if they differ.
3. **Line it up with your video.** Find any one slide in your footage, open *Line up with my video*, and enter which clip and time you saw it at. The offset is worked out for you, and every other slide then points at the right clip.
4. **Work down the list.** Each row says e.g. **Clip 3 at 00:06**. Hit *Not a slide* on false alarms. *Export CSV* saves the list.

To see the slides on the lap charts, open the same session in [Lap Compare](../lapcompare/README.md) and load that exported CSV there. The export carries a `session_id`, `session_start` and `source_lap` (RaceChrono's own lap number; the `lap` column restarts at 1) so the slides land on the right laps.

### The command line

```
.venv/bin/slidefinder session.rcz
.venv/bin/slidefinder session.rcz --sensitivity balanced --top 10
.venv/bin/slidefinder session.rcz --offset -12.5 --clip-length 12:48,12:47
```

It prints the ranked table and writes `slides.csv`. `--help` lists everything, including the advanced thresholds.

## How a slide is found

**With a steering angle** (logged from the car's CAN bus): a slide is a stretch where you steer one way while the car actually rotates the other way (opposite lock). A quick counter-steer that cancels a slide is *not* counted: the mismatch has to be sustained.

**Without a steering angle**: SlideFinder estimates how sideways the car is from the gyro and GPS heading, and reports stretches where the car points well away from where it is travelling. This is a different definition. On the one session it was tested against, it found roughly half to two thirds of the same slides and around 70% of its own matched one, so treat it as a useful second opinion, not a copy of the steering result. It can under-report a slide held perfectly straight with almost no rotation.

Severity ranks slides within a session: how long the slide lasted multiplied by how hard the car was rotating. It is not a measure of danger or speed.

Times count from when you actually start driving on track. The start is detected from GPS speed (the pit-exit launch), so time zero is not the moment you pressed record.

## Tracks and sectors

Sectors come from the RaceChrono track file (`.rcz`) for the circuit. SlideFinder reads the track name from your session and uses a matching track file if it has one. Sonoma is included. For another circuit, add its `.rcz` from the page (*Add a track file*) or copy it to `~/.slidefinder/tracks/`. Without one everything still works, just without sector names.

## What it supports

**Use the `.rcz` session file if you can.** It is the file RaceChrono saves, about a tenth the size of a CSV export (20 MB against 250 MB for one session), and it loads roughly nine times faster. It also carries the track, so sectors work without a separate track file.

- **Session archives (`.rcz`).** A session can hold several drives (the first, then each time you resumed). SlideFinder lists them as *parts* and analyses the one with the most laps by default; pick another from the *Part* menu (`--part N` on the command line). Lap numbers restart from 1 within the chosen part.
- **CSV exports** (format 3), with GPS position and speed at minimum.
- Both have been tried on a single session (40 minutes, 19 laps, a car with CAN steering), and the two readers give the same slides on it: same laps, sectors and clips, start times within 0.02 s. Other loggers, channel sets or app versions may not read correctly. If one doesn't, the error will say what's missing; please report it.
- RaceChrono's *calculated* channels (calculated speed, lean angle and so on) are only in CSV exports, so the lap charts from an `.rcz` don't list them. The raw GPS, accelerometer, gyro and CAN channels are all there.
- RaceChrono's own channel numbers are used to name the CAN channels, and the table (`CAN_CHANNELS` in `rcz.py`) was built from one car's export. A channel number it doesn't know is skipped, so an unusual setup may be missing some signals, but not steering unless it is logged under a different number.
- GoPro video is not read. You line clips up by hand once (step 3 above); there is no automatic sync and no clip cutting.

## Development

From the repository root:

```
.venv/bin/pip install -e packages/racelog -e "packages/slidefinder[dev]"
.venv/bin/python -m pytest packages/slidefinder
```

The `.rcz` layout isn't documented by RaceChrono; it was worked out by comparing one archive with its CSV export, and `rcz.py` explains what is known.

The browser tests need Chromium for Playwright (`.venv/bin/python -m playwright install chromium`) and are skipped without it. A few tests compare against a private real session and are skipped if it isn't present (set `SLIDEFINDER_GOLDEN_CSV` and `SLIDEFINDER_GOLDEN_RCZ` to point at the same session in each format).

Layout: `src/slidefinder/` holds the two detectors (`detect/`), threshold presets (`presets.py`), the results table (`report.py`), video mapping (`sync.py`), the command line (`cli.py`) and the web app (`server.py`, `web/`). Reading sessions and tracks lives in [`racelog`](../racelog/README.md).
