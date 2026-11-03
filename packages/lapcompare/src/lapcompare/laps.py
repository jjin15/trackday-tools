"""Per-lap data resampled by distance, for comparing laps in the viewer."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from racelog import rcz
from racelog.racechrono import read_header

SKIP = {"timestamp", "fragment_id", "lap_number", "elapsed_time", "distance_traveled",
        "device_battery_level", "device_update_rate", "fix_type", "satellites",
        "accuracy", "latitude", "longitude"}
GROUPS = {"gps": "GPS", "calc": "Calculated", "canbus": "CAN bus",
          "acc": "Accelerometer", "gyro": "Gyro"}
UNITS = {"m/s": ("mph", 2.23694), ".C": ("°C", 1.0), "deg": ("°", 1.0)}


def read_columns(path) -> Tuple[List[Tuple[int, str, str, float, str]], int]:
    """Return ([(index, key, unit, factor, group)] for plottable columns, first data line)."""
    header = read_header(path)
    counts: Dict[str, int] = {}
    for c in header.columns:
        counts[c.name] = counts.get(c.name, 0) + 1
    cols = []
    for c in header.columns:
        if c.name in SKIP:
            continue
        key = c.name.replace("_", " ")
        if counts[c.name] > 1:
            key += f" ({c.source})"
        unit, factor = UNITS.get(c.unit, (c.unit, 1.0))
        cols.append((c.index, key, unit, factor, GROUPS.get(c.source, c.source)))
    return cols, header.data_start


def _finish(laps, times, values, meta, step) -> dict:
    """Drop signals with nothing to compare and pick the default laps to show."""
    signals = []
    for key, (unit, group) in meta.items():
        flat = np.array([v for lap in values[key] for v in lap if v is not None], dtype=float)
        if flat.size == 0 or flat.std() == 0:
            del values[key]  # all-missing or constant: nothing to compare
            continue
        signals.append({"key": key, "unit": unit, "group": group})
    candidates = laps[1:-1] if len(laps) > 4 else laps
    default_laps = [l["n"] for l in sorted(candidates, key=lambda l: l["time"])[:3]]
    return {"step": step, "laps": laps, "signals": signals, "values": values,
            "time": times, "defaultLaps": default_laps}


def _listify(arr) -> list:
    return [None if np.isnan(v) else v for v in np.round(arr, 2)]


def build_data_rcz(path, step: float = 5.0, part: Optional[int] = None) -> dict:
    """Lap data straight from an .rcz: each channel is sampled where the lap's distance grid falls."""
    parts = rcz.list_parts(path)
    chosen = parts[rcz.default_part(parts) if part is None else part]
    ch = rcz.Channels(path, chosen)
    if not chosen.laps:
        return {"step": step, "laps": [], "signals": [], "values": {}, "time": [], "defaultLaps": []}
    base = chosen.laps[0].number - 1

    # (key, unit, group, times ms, values in display units, hold last value between samples)
    sources = []
    if ch.altitude is not None:
        sources.append(("altitude", "m", "GPS", ch.gps_t, ch.altitude, False))
    if ch.bearing is not None:
        sources.append(("bearing", "\u00b0", "GPS", ch.gps_t, ch.bearing, False))
    sources.append(("speed (gps)", "mph", "GPS", ch.gps_t, ch.speed * rcz.MPH_PER_MS, False))
    for name, group, imu in (("acc", "Accelerometer", ch.acc), ("rate of rotation", "Gyro", ch.gyro)):
        if imu is not None:
            unit = "G" if name == "acc" else "deg/s"
            for axis, v in zip("xyz", imu[1]):
                sources.append((f"{axis} {name}", unit, group, imu[0], v, False))
    for pid, (t, v) in ch.can.items():
        spec = rcz.CAN_CHANNELS[pid]
        sources.append((spec.key, spec.unit, "CAN bus", t, v * spec.factor, spec.step))
    sources.sort(key=lambda s: ({"GPS": 0, "Accelerometer": 2, "Gyro": 3}.get(s[2], 1), s[0]))

    laps, times = [], []
    values = {s[0]: [] for s in sources}
    for lap in chosen.laps:
        end = lap.end_ms if lap.end_ms is not None else chosen.last_ms
        inside = (ch.gps_t >= lap.start_ms) & (ch.gps_t <= end)
        if inside.sum() < 2:
            continue
        t = ch.gps_t[inside]
        d = np.maximum.accumulate(ch.gps_dist[inside] - ch.gps_dist[inside][0])
        grid = np.arange(int(d[-1] // step) + 1) * step
        at = np.interp(grid, d, t)                 # when the car was at each grid distance
        laps.append({"n": int(lap.number - base), "source": int(lap.number),
                     "time": round((end - lap.start_ms) / 1000.0, 3)})
        times.append(np.round((at - lap.start_ms) / 1000.0, 3).tolist())
        for key, _, _, st, sv, hold in sources:
            values[key].append(_listify(rcz.interp(st, sv, at, hold)))
    meta = {s[0]: (s[1], s[2]) for s in sources}
    return _finish(laps, times, values, meta, step)


def build_data(path, step: float = 5.0, part: Optional[int] = None) -> dict:
    """Every plottable signal for every lap on a common distance grid (`step` metres)."""
    if rcz.is_rcz(path):
        return build_data_rcz(path, step, part)
    cols, data_start = read_columns(path)
    df = pd.read_csv(path, skiprows=data_start, header=None, low_memory=False)
    lap_col = df[2]
    lap_ids = sorted(lap_col.dropna().unique())
    if not lap_ids:
        return {"step": step, "laps": [], "signals": [], "values": {}, "time": [], "defaultLaps": []}
    base = lap_ids[0] - 1  # relabel so the first lap is lap 1

    laps, times = [], []
    values: Dict[str, list] = {key: [] for _, key, *_ in cols}
    for lap_id in lap_ids:
        sub = df[lap_col == lap_id]
        t = sub[0].to_numpy()
        dist = sub[4].to_numpy()
        d = np.maximum.accumulate(dist - dist[0])
        grid = np.arange(int(d[-1] // step) + 1) * step
        laps.append({"n": int(lap_id - base), "source": int(lap_id), "time": round(float(t[-1] - t[0]), 3)})
        times.append(np.round(np.interp(grid, d, t - t[0]), 3).tolist())
        for i, key, _, factor, _ in cols:
            y = sub[i].to_numpy(dtype=float) * factor
            m = ~np.isnan(y)
            arr = np.interp(grid, d[m], y[m]) if m.sum() >= 2 else np.full(len(grid), np.nan)
            values[key].append([None if np.isnan(v) else v for v in np.round(arr, 2)])

    return _finish(laps, times, values, {key: (unit, group) for _, key, unit, _, group in cols}, step)
