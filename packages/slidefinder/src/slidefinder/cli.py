"""Command line: `slidefinder SESSION.csv`."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from .detect.auto import DetectionUnavailable, detect
from .detect.steering import calibrate
from .presets import DEFAULT_PRESET, PRESETS
from racelog import loader
from racelog.start import detect_start
from racelog.tracks import TrackError, find_track, load_gates, match_session_track
from racelog.util import fmt_time
from .report import build_events, rank_events
from .sync import parse_clip_lengths

DESCRIPTION = """Find slides/drifts in a RaceChrono CSV export.

A slide is a sustained period where the steering input and the car's actual rotation
point in opposite directions (opposite lock). Quick counter-steers are ignored."""


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="slidefinder", description=DESCRIPTION,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", help="RaceChrono session: an .rcz archive (much smaller) or a CSV export. "
                                    "Use `slidefinder serve` for the web app instead")
    ap.add_argument("--out", default="slides.csv", help="where to write the results (default slides.csv)")
    ap.add_argument("--top", type=int, default=0, help="only print the N most severe slides")
    ap.add_argument("--sensitivity", choices=sorted(PRESETS), default=DEFAULT_PRESET,
                    help="how readily slides are reported. "
                         + " ".join(f"{k}: {v.summary}" for k, v in PRESETS.items())
                         + " (default %(default)s)")
    ap.add_argument("--offset", type=float, default=0.0,
                    help="seconds added to data time to get video time; positive if the video "
                         "started before the data, negative if after")
    ap.add_argument("--clip-length", default="12:48",
                    help="length of each video file as mm:ss, or a comma-separated list if they "
                         "differ (the last value repeats); 'none' skips the clip columns")
    ap.add_argument("--track", help="track name or .rcz path; default is the track stored in the session "
                                    "(or a known one with the same name), 'none' turns sectors off")
    ap.add_argument("--part", type=int, help=".rcz only: which part of the session to analyse (1, 2, ...). "
                                             "Default is the one with the most laps")
    ap.add_argument("--sort", choices=["severity", "time"], default="severity",
                    help="most severe first (default) or chronological")
    adv = ap.add_argument_group("advanced")
    adv.add_argument("--method", choices=["auto", "steering", "slip"], default="auto",
                     help="how to find slides: from steering vs rotation, or from slip angle when "
                          "there's no steering data (default auto)")
    adv.add_argument("--min-slip", type=float, help="slip method only: minimum slip angle, degrees")
    adv.add_argument("--min-speed", type=float, help="m/s, ignore slower driving")
    adv.add_argument("--min-steer", type=float, help="minimum steering angle, degrees")
    adv.add_argument("--min-yaw", type=float, help="minimum opposite-direction rotation, deg/s")
    adv.add_argument("--min-duration", type=float, help="seconds; shorter is treated as counter-steer")
    adv.add_argument("--merge-gap", type=float, help="seconds; closer events are merged")
    adv.add_argument("--start-time", type=float,
                     help="seconds from the first data sample to treat as time zero (overrides detection)")
    adv.add_argument("--no-trim", action="store_true",
                     help="keep time zero at the first data sample instead of the on-track start")
    adv.add_argument("--pit-speed", type=float, default=5.0,
                     help="m/s; below this the car counts as in the pits or stopped")
    adv.add_argument("--keep-lap-numbers", action="store_true",
                     help="use RaceChrono's lap numbers instead of renumbering from 1")
    adv.add_argument("--hz", type=int, default=50, help="analysis sample rate")
    return ap


def run(args) -> int:
    parts = loader.list_parts(args.session)
    if args.part is not None and not 1 <= args.part <= len(parts):
        raise LookupError(f"--part must be between 1 and {len(parts)} for this file.")
    part = args.part - 1 if args.part else loader.default_part(args.session)
    session = loader.load_session(args.session, args.hz, part)
    print(f"Loaded {len(session.df)} samples ({session.duration / 60:.1f} min).")
    if len(parts) > 1:
        print(f"This file has {len(parts)} parts: " + "; ".join(p.label for p in parts)
              + f". Analysing part {part + 1}" + ("" if args.part else " (most laps); choose another with --part")
              + ".")
    overrides = {"min_speed": args.min_speed, "min_steer": args.min_steer, "min_yaw": args.min_yaw,
                 "min_duration": args.min_duration, "merge_gap": args.merge_gap,
                 "min_slip": args.min_slip}
    detection = detect(session, args.sensitivity, args.method, **overrides)
    print(detection.note)
    if detection.method == "steering":
        sign, slope = calibrate(session, overrides["min_speed"] or PRESETS[args.sensitivity].params.min_speed)
        if slope == 0.0:
            print("Not enough driving above the minimum speed to calibrate steering, so no slides.")
            return 0
        print(f"Steering sign {'+' if sign > 0 else '-'}, {slope:.3f} deg/s yaw per deg steer.")

    gates = None
    if args.track and args.track.lower() != "none":
        track = find_track(args.track)
        gates = load_gates(track.path)
    elif not args.track:
        track = loader.embedded_track(args.session) or match_session_track(session.track_name)
        if track:
            gates = load_gates(track.path)
            print(f"Track: {track.name}")
        elif session.track_name:
            print(f"No track file for '{session.track_name}', so sectors are skipped "
                  f"(add one with --track path/to/file.rcz).")

    if args.no_trim:
        t_zero = 0.0
    elif args.start_time is not None:
        t_zero = args.start_time
    else:
        t_zero = detect_start(session, pit_speed=args.pit_speed)
    if t_zero:
        row = session.df.iloc[(session.df["t"] - t_zero).abs().argmin()]
        utc = datetime.fromtimestamp(session.t0 + t_zero, timezone.utc).strftime("%H:%M:%S")
        print(f"On-track start at {fmt_time(t_zero)} into the data ({utc} UTC, "
              f"{row['latitude']:.5f}, {row['longitude']:.5f}); times below are measured from there.")

    runs = detection.runs
    clip_lengths = None if args.clip_length.lower() == "none" else parse_clip_lengths(args.clip_length)
    events = build_events(session, runs, gates=gates, t_zero=t_zero, offset=args.offset,
                          clip_lengths=clip_lengths, relabel_laps=not args.keep_lap_numbers)
    if events.empty:
        print("No slides found. Try a looser --sensitivity (balanced or loose).")
        return 0
    events = rank_events(events, args.sort)
    events.to_csv(args.out, index=False)
    show = events.head(args.top) if args.top else events
    print(f"{len(events)} slides -> {args.out}\n")
    print(show.drop(columns=["lat", "lon", "session_time_s"]).to_string(index=False))
    return 0


def serve_main(argv) -> int:
    ap = argparse.ArgumentParser(prog="slidefinder serve",
                                 description="Run the SlideFinder web app on this computer.")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="don't open a browser tab")
    args = ap.parse_args(argv)
    from .server import serve

    serve(args.port, open_browser=not args.no_open)
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] == "serve":
        return serve_main(argv[1:])
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except (*loader.FormatError, DetectionUnavailable, TrackError, LookupError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    except OSError as err:                      # a mistyped path, a folder, no permission
        print(f"Error: couldn't open {err.filename or 'the file'}: {err.strerror or err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
