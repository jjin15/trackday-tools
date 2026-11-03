"""Read RaceChrono CSV exports (format 3)."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .session import Session

MAX_PREAMBLE = 60  # rows to scan for the column header


class RaceChronoFormatError(ValueError):
    """The file isn't a RaceChrono CSV this tool can read."""


@dataclass
class Column:
    index: int
    name: str
    unit: str
    source: str   # e.g. "gps", "canbus", "calc", "acc", "gyro"


@dataclass
class Header:
    meta: Dict[str, str]
    columns: List[Column]
    data_start: int   # zero-based line number of the first data row

    def find(self, name: str, prefer_source: Optional[str] = None) -> Optional[Column]:
        """First column called `name`, preferring one from `prefer_source` when given."""
        matches = [c for c in self.columns if c.name == name]
        if prefer_source:
            for c in matches:
                if c.source == prefer_source:
                    return c
        return matches[0] if matches else None


def read_header(path) -> Header:
    """Parse the metadata block, then the column names, units and sources."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        for _ in range(MAX_PREAMBLE):
            try:
                rows.append(next(reader))
            except StopIteration:
                break
    header_at = next((i for i, r in enumerate(rows) if r and r[0] == "timestamp"), None)
    if header_at is None or header_at + 2 >= len(rows):
        raise RaceChronoFormatError(
            "Couldn't find the column header. Is this a RaceChrono CSV export (format 3)?")
    meta = {r[0].strip().lower(): r[1].strip() for r in rows[:header_at] if len(r) >= 2 and r[0]}
    names, units, sources = rows[header_at], rows[header_at + 1], rows[header_at + 2]
    columns = []
    for i, name in enumerate(names):
        unit = units[i] if i < len(units) else ""
        source = sources[i].split(":")[-1].strip() if i < len(sources) else ""
        columns.append(Column(i, name, unit, source))
    return Header(meta, columns, header_at + 3)


REQUIRED = ["timestamp", "latitude", "longitude", "speed"]
# (output name in the raw frame, RaceChrono column name, preferred source)
CHANNELS = [
    ("timestamp", "timestamp", None),
    ("lap_number", "lap_number", None),
    ("latitude", "latitude", None),
    ("longitude", "longitude", None),
    ("speed", "speed", "gps"),
    ("steering_angle", "steering_angle", None),
    ("z_rate_of_rotation", "z_rate_of_rotation", None),
    # used by the no-steering detector
    ("bearing", "bearing", "gps"),
    ("x_acc", "x_acc", None), ("y_acc", "y_acc", None), ("z_acc", "z_acc", None),
    ("x_rate_of_rotation", "x_rate_of_rotation", None),
    ("y_rate_of_rotation", "y_rate_of_rotation", None),
]
OPTIONAL = ["lap_number", "steering_angle", "z_rate_of_rotation", "bearing", "x_acc", "y_acc",
            "z_acc", "x_rate_of_rotation", "y_rate_of_rotation"]


def load_session(path, hz: int = 50) -> Session:
    """Read the channels the analysis needs and resample them to `hz` by time-binning."""
    header = read_header(path)
    picked = {}
    for out_name, name, source in CHANNELS:
        col = header.find(name, source)
        if col is not None:
            picked[out_name] = col.index
    missing = [n for n in REQUIRED if n not in picked]
    if missing:
        raise RaceChronoFormatError(
            f"The file is missing required channels: {', '.join(missing)}. "
            "GPS position and speed are required at minimum.")

    df = pd.read_csv(path, skiprows=header.data_start, header=None,
                     usecols=list(picked.values()), low_memory=False)
    df.columns = [n for n, _ in sorted(picked.items(), key=lambda kv: kv[1])]
    for optional in OPTIONAL:
        if optional not in df:
            df[optional] = np.nan
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        raise RaceChronoFormatError("The file has no data rows.")
    t0 = float(df["timestamp"].iloc[0])
    df["t"] = df["timestamp"] - t0
    bins = np.floor(df["t"] * hz).astype(np.int64)
    heading = np.radians(df["bearing"])   # compass bearings are averaged as vectors
    df["bearing_sin"], df["bearing_cos"] = np.sin(heading), np.cos(heading)
    out = df.groupby(bins).agg(
        t=("t", "mean"), lap_number=("lap_number", "max"),
        latitude=("latitude", "mean"), longitude=("longitude", "mean"),
        speed=("speed", "mean"), steer=("steering_angle", "mean"),
        yaw=("z_rate_of_rotation", "mean"),
        bearing_sin=("bearing_sin", "mean"), bearing_cos=("bearing_cos", "mean"),
        ax=("x_acc", "mean"), ay=("y_acc", "mean"), az=("z_acc", "mean"),
        gx=("x_rate_of_rotation", "mean"), gy=("y_rate_of_rotation", "mean"),
        gz=("z_rate_of_rotation", "mean")).reset_index(drop=True)
    out["bearing"] = np.degrees(np.arctan2(out.pop("bearing_sin"), out.pop("bearing_cos"))) % 360
    out.loc[df["bearing"].groupby(bins).count().to_numpy() == 0, "bearing"] = np.nan
    return Session(df=out, t0=t0, hz=hz, meta=header.meta)
