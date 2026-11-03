"""The parsed, resampled session that every analysis step works on."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict

import pandas as pd


@dataclass
class Session:
    """A RaceChrono session resampled to a fixed rate.

    `df` has one row per 1/hz seconds and columns t (seconds from the first sample),
    lap_number, latitude, longitude, speed (GPS, m/s), steer (deg) and yaw (deg/s), plus
    bearing (GPS course, deg) and raw IMU axes ax/ay/az (G) and gx/gy/gz (deg/s).
    Channels the log doesn't contain are all-NaN.
    """
    df: pd.DataFrame
    t0: float                      # unix time of the first sample
    hz: int
    meta: Dict[str, str] = field(default_factory=dict)

    @property
    def has_steering(self) -> bool:
        return bool(self.df["steer"].notna().any())

    @property
    def has_yaw(self) -> bool:
        return bool(self.df["yaw"].notna().any())

    @property
    def has_slip_inputs(self) -> bool:
        """Whether the no-steering detector can run: GPS heading plus a yaw rate source."""
        return bool(self.df["bearing"].notna().any() and
                    (self.df["yaw"].notna().any() or self.df[["gx", "gy", "gz"]].notna().any().all()))

    @property
    def track_name(self) -> str:
        return self.meta.get("track name", "")

    @property
    def duration(self) -> float:
        return float(self.df["t"].iloc[-1])

    @property
    def fingerprint(self) -> str:
        """A short id that stays the same for the same recorded data, whichever file format it
        was read from and whichever analysis rate was used.

        It is built from the track name and the first GPS timestamp (rounded to the second,
        because the CSV and the .rcz start a few milliseconds apart). Parts of one .rcz differ
        in start time, so each part gets its own id.
        """
        key = f"{self.track_name.strip().lower()}|{round(self.t0)}"
        return hashlib.sha1(key.encode()).hexdigest()[:12]
