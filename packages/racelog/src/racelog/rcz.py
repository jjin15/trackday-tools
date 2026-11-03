"""Read RaceChrono session archives (.rcz) directly, so no CSV export is needed.

An .rcz is a zip holding `session.json` (laps and track name), `trackId.json` (the track),
and for each part of the session a folder of binary channel files: the first drive at the
top level, each later resume in `resume_N/`. Every channel is its own file at its own sample
rate; RaceChrono's CSV export is just these resampled onto one 500 Hz grid by linear
interpolation, which is why reading them here reproduces the CSV values.

File names are `channel_<device type>_<device id>_0_<channel>_<kind>` for GPS and the IMU, and
`channel_<type>_<id>_<pid>_1_1` (times) with `channel2_<type>_<id>_<pid>_<pid>_3` (values)
for CAN bus channels. Layouts were worked out by comparing one archive with its CSV export.
"""
from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from .session import Session

GPS_TYPE, ACC_TYPE, GYRO_TYPE, CAN_TYPE = 1, 2, 3, 12
G_IN_RAW = 9806.65            # accelerometer samples are stored in mm/s^2
MPH_PER_MS = 2.23694

# GPS channel numbers (int32 samples unless noted)
GPS_TIME, GPS_DISTANCE, GPS_POSITION = 1, 2, 3     # int64 ms, int64 mm, int32 lat/lon pairs
GPS_SPEED, GPS_ALTITUDE, GPS_BEARING = 4, 5, 6     # thousandths of m/s, m, degrees
ACC_AXES = (9, 10, 11)                             # x, y, z in mm/s^2
GYRO_AXES = (12, 13, 14)                           # x, y, z in thousandths of deg/s


class RczFormatError(ValueError):
    """The file isn't a RaceChrono session archive this tool can read."""


@dataclass(frozen=True)
class CanChannel:
    key: str                  # the name used in the lap viewer (same as the CSV export's)
    unit: str                 # unit shown to people
    factor: float = 1.0       # display = value * factor
    step: bool = False        # hold the last value between samples instead of interpolating


# RaceChrono's built-in channel numbers, matched against a CSV export of the same session.
CAN_CHANNELS: Dict[int, CanChannel] = {
    4: CanChannel("speed (canbus)", "mph", MPH_PER_MS),
    7: CanChannel("lateral acc (canbus)", "G", 1.0 / 9.80665),          # stored in m/s^2
    8: CanChannel("longitudinal acc (canbus)", "G", 1.0 / 9.80665),
    38: CanChannel("pitch", "°"),
    1001: CanChannel("steering angle", "°"),
    1002: CanChannel("brake pos", "%"),
    1004: CanChannel("gear", "", step=True),
    1029: CanChannel("engine torque", "Nm"),
    5017: CanChannel("torque", "Nm"),
    10024: CanChannel("rpm", "rpm"),
    10025: CanChannel("throttle pos", "%"),
    10026: CanChannel("coolant temp", "°C"),
    10031: CanChannel("air temp", "°C"),
    10066: CanChannel("engine oil temp", "°C"),
    10071: CanChannel("accelerator pos", "%"),
    33801: CanChannel("brake pressure rear", "kPa"),
    66569: CanChannel("brake pressure front", "kPa"),
    99320: CanChannel("wheel speed freq rr", "Hz"),
    132088: CanChannel("wheel speed freq rl", "Hz"),
    164856: CanChannel("wheel speed freq fr", "Hz"),
    197624: CanChannel("wheel speed freq fl", "Hz"),
}
STEERING_PID = 1001


@dataclass
class Lap:
    number: int
    start_ms: int
    end_ms: Optional[int]     # None for a lap that was still running when logging stopped


@dataclass
class Part:
    """One continuous stretch of logging: the first drive, or a later resume."""
    index: int                # 0 for the first drive, N for resume_N
    prefix: str               # "" or "resume_N/"
    first_ms: int
    last_ms: int
    laps: List[Lap]

    @property
    def minutes(self) -> float:
        return (self.last_ms - self.first_ms) / 60000.0

    @property
    def label(self) -> str:
        if not self.laps:
            return f"Part {self.index + 1}: no laps ({self.minutes:.0f} min)"
        first, last = self.laps[0].number, self.laps[-1].number
        laps = f"lap {first}" if first == last else f"laps {first}–{last}"
        return f"Part {self.index + 1}: {laps} ({self.minutes:.0f} min)"


def is_rcz(path) -> bool:
    """Whether `path` is a zip file (the container every .rcz uses)."""
    try:
        with open(path, "rb") as fh:
            return fh.read(4) == b"PK\x03\x04"
    except OSError:
        return False


def _json(z: zipfile.ZipFile, name: str) -> dict:
    try:
        return json.loads(z.read(name))
    except KeyError:
        raise RczFormatError(f"This archive has no {name}, so it isn't a RaceChrono session.")
    except ValueError:
        raise RczFormatError(f"{name} in this archive couldn't be read.")


def _open(path) -> zipfile.ZipFile:
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise RczFormatError("That file isn't a valid .rcz archive.")
    if "session.json" not in z.namelist():
        z.close()
        raise RczFormatError("That looks like a track file, not a session. "
                             "Open a session .rcz (or a CSV export).")
    return z


def read_session_meta(path) -> dict:
    with _open(path) as z:
        return _json(z, "session.json")


def list_parts(path) -> List[Part]:
    """The parts of a session in order, each with the laps that were driven in it."""
    with _open(path) as z:
        meta = _json(z, "session.json")
        names = set(z.namelist())
        prefixes = [("", 0)] if "sessionfragment.json" in names else []
        for name in sorted(names):
            m = re.fullmatch(r"resume_(\d+)/sessionfragment\.json", name)
            if m:
                prefixes.append((f"resume_{m.group(1)}/", int(m.group(1))))
        parts = []
        for prefix, index in sorted(prefixes, key=lambda p: p[1]):
            frag = _json(z, prefix + "sessionfragment.json")
            laps = [Lap(int(l["number"]), int(l["startTimestamp"]), l.get("finishTimestamp"))
                    for l in meta.get("laps", []) if int(l.get("sessionResume", 0)) == index]
            parts.append(Part(index, prefix, int(frag["firstTimestamp"]), int(frag["latestTimestamp"]),
                              sorted(laps, key=lambda l: l.number)))
    if not parts:
        raise RczFormatError("This archive has no recorded data.")
    return parts


def default_part(parts: List[Part]) -> int:
    """Index into `parts` of the part with the most laps (the latest one on a tie)."""
    return max(range(len(parts)), key=lambda i: (len(parts[i].laps), i))


def _devices(z: zipfile.ZipFile, part: Part) -> Dict[int, int]:
    """Device type -> device id for this part."""
    frag = _json(z, part.prefix + "sessionfragment.json")
    return {int(d["selector"]["type"]): int(d["selector"]["id"]) for d in frag.get("devices2", [])}


def _read(z: zipfile.ZipFile, part: Part, name: str, dtype: str) -> Optional[np.ndarray]:
    try:
        return np.frombuffer(z.read(part.prefix + name), dtype=dtype)
    except KeyError:
        return None


class Channels:
    """Every channel of one part, each as (times in ms, values in display units)."""

    def __init__(self, path, part: Part):
        self.part = part
        with _open(path) as z:
            devs = _devices(z, part)
            gps = devs.get(GPS_TYPE)
            if gps is None:
                raise RczFormatError("This session has no GPS data, which is required.")
            base = f"channel_{GPS_TYPE}_{gps}_0_"
            t = _read(z, part, f"{base}{GPS_TIME}_1", "<i8")
            dist = _read(z, part, f"{base}{GPS_DISTANCE}_1", "<i8")
            pos = _read(z, part, f"{base}{GPS_POSITION}_1", "<i4")
            speed = _read(z, part, f"{base}{GPS_SPEED}_0", "<i4")
            if t is None or pos is None or speed is None or len(t) < 2:
                raise RczFormatError("The GPS data in this session is missing or too short.")
            n = min(len(t), len(pos) // 2, len(speed), len(dist) if dist is not None else len(t))
            self.gps_t = t[:n].astype(float)
            self.gps_dist = (dist[:n] / 1000.0) if dist is not None else np.zeros(n)
            lat_lon = pos[: 2 * n].reshape(-1, 2) / 6e6
            self.lat, self.lon = lat_lon[:, 0], lat_lon[:, 1]
            self.speed = speed[:n] / 1000.0
            alt = _read(z, part, f"{base}{GPS_ALTITUDE}_0", "<i4")
            brg = _read(z, part, f"{base}{GPS_BEARING}_0", "<i4")
            self.altitude = alt[:n] / 1000.0 if alt is not None and len(alt) >= n else None
            self.bearing = brg[:n] / 1000.0 if brg is not None and len(brg) >= n else None

            self.acc = self._imu(z, part, devs.get(ACC_TYPE), ACC_TYPE, ACC_AXES, 1.0 / G_IN_RAW)
            self.gyro = self._imu(z, part, devs.get(GYRO_TYPE), GYRO_TYPE, GYRO_AXES, 1.0 / 1000.0)

            self.can: Dict[int, Tuple[np.ndarray, np.ndarray]] = {}
            can_id = devs.get(CAN_TYPE)
            if can_id is not None:
                for pid in CAN_CHANNELS:
                    times = _read(z, part, f"channel_{CAN_TYPE}_{can_id}_{pid}_1_1", "<i8")
                    vals = _read(z, part, f"channel2_{CAN_TYPE}_{can_id}_{pid}_{pid}_3", "<f8")
                    if times is not None and vals is not None and len(times) >= 2:
                        k = min(len(times), len(vals))
                        self.can[pid] = (times[:k].astype(float), vals[:k])

    @staticmethod
    def _imu(z, part, dev_id, dev_type, axes, scale):
        if dev_id is None:
            return None
        t = _read(z, part, f"channel_{dev_type}_{dev_id}_0_1_1", "<i8")
        cols = [_read(z, part, f"channel_{dev_type}_{dev_id}_0_{a}_0", "<i4") for a in axes]
        if t is None or any(c is None for c in cols) or len(t) < 2:
            return None
        n = min(len(t), *(len(c) for c in cols))
        return t[:n].astype(float), [c[:n] * scale for c in cols]

    @property
    def has_steering(self) -> bool:
        return STEERING_PID in self.can


def interp(t_ms: np.ndarray, v: np.ndarray, at_ms: np.ndarray, step: bool = False) -> np.ndarray:
    """Values at `at_ms` (NaN outside the channel's own time range)."""
    if step:
        i = np.searchsorted(t_ms, at_ms, side="right") - 1
        out = v[np.clip(i, 0, len(v) - 1)].astype(float)
        out[i < 0] = np.nan
    else:
        out = np.interp(at_ms, t_ms, v)
    out[(at_ms < t_ms[0]) | (at_ms > t_ms[-1])] = np.nan
    return out


def _bearing_at(ch: Channels, at_ms: np.ndarray) -> np.ndarray:
    if ch.bearing is None:
        return np.full(len(at_ms), np.nan)
    rad = np.radians(ch.bearing)    # compass bearings are interpolated as vectors, not numbers
    s, c = interp(ch.gps_t, np.sin(rad), at_ms), interp(ch.gps_t, np.cos(rad), at_ms)
    return np.degrees(np.arctan2(s, c)) % 360.0


def lap_numbers_at(part: Part, at_ms: np.ndarray) -> np.ndarray:
    """RaceChrono's lap number at each time (NaN between laps)."""
    out = np.full(len(at_ms), np.nan)
    for lap in part.laps:
        end = lap.end_ms if lap.end_ms is not None else part.last_ms
        out[(at_ms >= lap.start_ms) & (at_ms < end)] = lap.number
    return out


def load_session(path, hz: int = 50, part: Optional[int] = None) -> Session:
    """Resample one part of an .rcz to `hz` and return it as a Session.

    `part` is an index into list_parts(); by default the part with the most laps.
    """
    parts = list_parts(path)
    chosen = parts[default_part(parts) if part is None else part]
    meta = read_session_meta(path)
    ch = Channels(path, chosen)

    first_ms, last_ms = ch.gps_t[0], ch.gps_t[-1]
    n = int((last_ms - first_ms) / 1000.0 * hz)
    if n < 2:
        raise RczFormatError("This part of the session is too short to analyse.")
    t = (np.arange(n) + 0.5) / hz                 # bin centres, the same as the CSV loader
    at = first_ms + t * 1000.0

    def can(pid):
        if pid not in ch.can:
            return np.full(n, np.nan)
        times, vals = ch.can[pid]
        return interp(times, vals, at, CAN_CHANNELS[pid].step)

    def imu(source, k):
        return np.full(n, np.nan) if source is None else interp(source[0], source[1][k], at)

    import pandas as pd
    df = pd.DataFrame({
        "t": t,
        "lap_number": lap_numbers_at(chosen, at),
        "latitude": interp(ch.gps_t, ch.lat, at),
        "longitude": interp(ch.gps_t, ch.lon, at),
        "speed": interp(ch.gps_t, ch.speed, at),
        "steer": can(STEERING_PID),
        "yaw": imu(ch.gyro, 2),
        "bearing": _bearing_at(ch, at),
        "ax": imu(ch.acc, 0), "ay": imu(ch.acc, 1), "az": imu(ch.acc, 2),
        "gx": imu(ch.gyro, 0), "gy": imu(ch.gyro, 1), "gz": imu(ch.gyro, 2),
    })
    return Session(df=df, t0=first_ms / 1000.0, hz=hz,
                   meta={"track name": meta.get("trackName", ""), "format": "rcz"})
