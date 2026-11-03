"""Synthetic RaceChrono data for tests: sessions with known events, and writers that save them
in RaceChrono's own formats (CSV export and .rcz archive).

Installed with the library so every package's tests can build the same fixtures. These are
test helpers, not part of the reading API.
"""
import csv
import json
import zipfile

import numpy as np
import pandas as pd

from .session import Session


def make_session(events, seconds=60, hz=50, speed=30.0, steering=True):
    """A synthetic session: gentle weaving at `speed` m/s where yaw follows steering
    (0.25 deg/s per degree), plus injected opposite-lock events.

    `events` is a list of (start_s, duration_s): during each the steering is held at +100 deg
    while the car rotates the other way at -30 deg/s.
    """
    t = np.arange(0, seconds, 1 / hz)
    steer = 60 * np.sin(2 * np.pi * t / 8.0)
    yaw = 0.25 * steer
    for start, dur in events:
        m = (t >= start) & (t < start + dur)
        steer[m], yaw[m] = 100.0, -30.0
    df = pd.DataFrame({
        "t": t, "lap_number": 1.0, "latitude": 38.0 + 1e-5 * t, "longitude": -122.0,
        "speed": speed, "steer": steer if steering else np.nan, "yaw": yaw})
    return Session(df=df, t0=1_700_000_000.0, hz=hz, meta={"track name": "Synthetic"})


def make_slip_session(seconds=60, hz=50, speed=30.0, slide=(25.0, 3.0), peak=20.0, gyro_sign=1.0):
    """Synthetic session with GPS course and gyro only (no steering channel).

    Two clean corners (+15 and -15 deg/s of course change) set the gyro sign, and a slide in a
    third corner where the car points `peak` degrees away from its course for `slide[1]` s.
    """
    t = np.arange(0, seconds, 1 / hz)
    course_rate = np.zeros_like(t)
    course_rate[(t >= 8) & (t < 13)] = 15.0
    course_rate[(t >= 40) & (t < 45)] = -15.0
    course_rate[(t >= 23) & (t < 30)] = 12.0     # the corner the slide happens in
    course = 90.0 + np.cumsum(course_rate) / hz
    beta = np.zeros_like(t)
    start, dur = slide
    ramp = 0.4
    up = (t >= start) & (t < start + ramp)
    hold = (t >= start + ramp) & (t < start + dur - ramp)
    down = (t >= start + dur - ramp) & (t < start + dur)
    beta[up] = peak * (t[up] - start) / ramp
    beta[hold] = peak
    beta[down] = peak * (start + dur - t[down]) / ramp
    heading = course + beta
    yaw = np.gradient(heading, 1 / hz)
    df = pd.DataFrame({
        "t": t, "lap_number": 1.0, "latitude": 38.0 + 1e-5 * t, "longitude": -122.0,
        "speed": speed, "steer": np.nan, "yaw": gyro_sign * yaw,
        "bearing": course % 360.0,
        "ax": 0.0, "ay": 0.0, "az": 1.0, "gx": 0.0, "gy": 0.0, "gz": gyro_sign * yaw})
    return Session(df=df, t0=1_700_000_000.0, hz=hz, meta={"track name": "Synthetic"})


# ------------------------------------------------------------ CSV and .rcz writers
COLUMNS = [
    # name, unit, source
    ("timestamp", "unix time", ""), ("fragment_id", "", ""), ("lap_number", "", ""),
    ("elapsed_time", "s", ""), ("distance_traveled", "m", ""), ("bearing", "deg", "gps"),
    ("latitude", "deg", "gps"), ("longitude", "deg", "gps"), ("speed", "m/s", "gps"),
    ("speed", "m/s", "calc"),                       # decoy: must not be used
    ("steering_angle", "deg", "canbus"),
    ("speed", "m/s", "canbus"),                     # decoy
    ("x_acc", "G", "acc"), ("y_acc", "G", "acc"), ("z_acc", "G", "acc"),
    ("x_rate_of_rotation", "deg/s", "gyro"), ("y_rate_of_rotation", "deg/s", "gyro"),
    ("z_rate_of_rotation", "deg/s", "gyro"),
]


def write_racechrono_csv(session, path, track="Synthetic Track", steering=True, drop=()):
    """Write `session` (a slidefinder Session) as a RaceChrono CSV. `drop` omits columns by name."""
    df = session.df
    keep = [i for i, (name, _, _) in enumerate(COLUMNS) if name not in drop and (steering or name != "steering_angle")]
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["This file is created using RaceChrono v10.2.4 ( http://racechrono.com/ )."])
        w.writerow(["Format", 3])
        w.writerow(["Session title", track])
        w.writerow(["Session type", "Lap timing"])
        w.writerow(["Track name", track])
        w.writerow(["Driver name", ""])
        w.writerow(["Created", "24/10/2026", "15:37"])
        w.writerow(["Note", ""])
        w.writerow([])
        w.writerow([COLUMNS[i][0] for i in keep])
        w.writerow([COLUMNS[i][1] for i in keep])
        w.writerow([f"100: {COLUMNS[i][2]}" if COLUMNS[i][2] else "" for i in keep])
        for k in range(len(df)):
            r = df.iloc[k]
            values = {
                0: session.t0 + r["t"], 1: 1, 2: r["lap_number"], 3: r["t"], 4: r["t"] * r["speed"],
                5: r.get("bearing", 0.0), 6: r["latitude"], 7: r["longitude"], 8: r["speed"],
                9: 0.0, 10: r["steer"], 11: 0.0,
                12: r.get("ax", 0.0), 13: r.get("ay", 0.0), 14: r.get("az", 1.0),
                15: r.get("gx", 0.0), 16: r.get("gy", 0.0), 17: r.get("gz", r["yaw"]),
            }
            w.writerow(["" if (isinstance(values[i], float) and np.isnan(values[i])) else
                        (round(values[i], 4) if isinstance(values[i], float) else values[i])
                        for i in keep])


# ---------------------------------------------------------------- .rcz (session archive) writer
GATE_SF = {"name": "S/F", "centerLatitude": int(38.0003 * 6e6), "centerLongitude": int(-122.0 * 6e6),
           "bearing": 0, "width": 100000, "type": 3}


def _i8(values):
    return np.asarray(values, dtype="<i8").tobytes()


def _i4(values):
    return np.asarray(values, dtype="<i4").tobytes()


def write_racechrono_rcz(path, sessions, laps, track_name="Synthetic Track", steering=True,
                         embedded_track=None, can_lateral_ms2=None):
    """Write one session archive. `sessions` is a list of slidefinder Sessions, one per part
    (the first at the top level, later ones in resume_N/); `laps[i]` lists
    (number, start_s, end_s or None) for part i, with times relative to that part's start.

    `embedded_track` is a list of gate dicts to store as trackId.json. `can_lateral_ms2`, if
    given, is written as the CAN lateral-acceleration channel (stored in m/s^2, as RaceChrono does).
    """
    session_laps = []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for index, sess in enumerate(sessions):
            prefix = "" if index == 0 else f"resume_{index}/"
            df = sess.df
            gps = df.iloc[::2]                                    # 25 Hz GPS from the 50 Hz frame
            t_ms = np.round((sess.t0 + gps["t"].to_numpy()) * 1000).astype(np.int64)
            dist_mm = np.round(np.cumsum(gps["speed"].to_numpy() * 0.04) * 1000)
            latlon = np.column_stack([gps["latitude"] * 6e6, gps["longitude"] * 6e6]).round().astype(np.int64)
            files = {
                "channel_1_100_0_1_1": _i8(t_ms),
                "channel_1_100_0_2_1": _i8(dist_mm),
                "channel_1_100_0_3_1": _i4(latlon.ravel()),
                "channel_1_100_0_4_0": _i4(np.round(gps["speed"] * 1000)),
                "channel_1_100_0_5_0": _i4(np.full(len(gps), 5000)),
                "channel_1_100_0_6_0": _i4(np.round(np.nan_to_num(gps.get("bearing", 0.0)) * 1000)),
            }
            imu = gps.copy()
            for col, default in (("ax", 0.0), ("ay", 0.0), ("az", 1.0), ("gx", 0.0), ("gy", 0.0)):
                if col not in imu:
                    imu[col] = default
            if "gz" not in imu:                                   # steering-style sessions only have a yaw rate
                imu["gz"] = imu["yaw"]
            for dev, dtype, axes, cols, scale in ((101, 2, (9, 10, 11), ("ax", "ay", "az"), 9806.65),
                                                   (102, 3, (12, 13, 14), ("gx", "gy", "gz"), 1000.0)):
                files[f"channel_{dtype}_{dev}_0_1_1"] = _i8(t_ms)
                for axis, col in zip(axes, cols):
                    files[f"channel_{dtype}_{dev}_0_{axis}_0"] = _i4(np.round(np.nan_to_num(imu[col]) * scale))
            if steering and df["steer"].notna().any():
                can = df.iloc[::10]                               # 5 Hz, like a real steering channel
                ct = np.round((sess.t0 + can["t"].to_numpy()) * 1000).astype(np.int64)
                files["channel_12_200_1001_1_1"] = _i8(ct)
                files["channel2_12_200_1001_1001_3"] = can["steer"].to_numpy("<f8").tobytes()
                files["channel_12_200_4_1_1"] = _i8(ct)
                files["channel2_12_200_4_4_3"] = can["speed"].to_numpy("<f8").tobytes()
                if can_lateral_ms2 is not None:
                    files["channel_12_200_7_1_1"] = _i8(ct)
                    files["channel2_12_200_7_7_3"] = np.full(len(can), can_lateral_ms2, dtype="<f8").tobytes()
            devices = [{"selector": {"id": 100, "model": 121, "type": 1}},
                       {"selector": {"id": 101, "model": 121, "type": 2}},
                       {"selector": {"id": 102, "model": 121, "type": 3}},
                       {"selector": {"id": 200, "model": 405, "type": 12}}]
            files["sessionfragment.json"] = json.dumps({
                "version": 1, "primaryGpsDeviceIndex": 100, "firstTimestamp": int(t_ms[0]),
                "latestTimestamp": int(t_ms[-1]), "devices2": devices}).encode()
            for name, data in files.items():
                z.writestr(prefix + name, data)
            for number, start, end in laps[index]:
                lap = {"number": number, "sessionResume": index,
                       "startTimestamp": int(round((sess.t0 + start) * 1000)), "isInvalid": False}
                if end is not None:
                    lap["finishTimestamp"] = int(round((sess.t0 + end) * 1000))
                session_laps.append(lap)
        z.writestr("session.json", json.dumps({"version": 1, "trackName": track_name, "laps": session_laps}))
        if embedded_track is not None:
            z.writestr("trackId.json", json.dumps({"track": {"name": track_name, "traps": embedded_track}}))


def write_two_part_rcz(path, **kw):
    """An archive with two parts: one lap, then (six hours later) two laps with a 3 s slide at t=30.

    Returns the two sessions it was built from. Extra keyword arguments go to write_racechrono_rcz.
    """
    import dataclasses

    first = make_session([])
    second = dataclasses.replace(make_session([(30.0, 3.0)]), t0=first.t0 + 6 * 3600)
    write_racechrono_rcz(path, [first, second], [[(1, 0.0, None)], [(2, 0.0, 30.0), (3, 30.0, None)]], **kw)
    return first, second
