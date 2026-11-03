"""Detect slides from opposite lock: steering one way while the car rotates the other.

A slide is a sustained period where the steering input and the car's actual rotation
(gyro yaw rate) point in opposite directions. Short opposite-sign blips are treated as
slide-cancelling counter-steer and dropped by `min_duration`.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np

from ..presets import DetectParams
from racelog.session import Session
from . import Run


MIN_CALIBRATION_SAMPLES = 100


def calibrate(session: Session, min_speed: float) -> Tuple[float, float]:
    """Return (sign, scale): +1/-1 so sign * steer matches yaw in normal driving, and
    the magnitude of deg/s of yaw per degree of steering.

    The scale is 0.0 when there isn't enough driving to calibrate from.
    """
    df = session.df
    m = (df["speed"] >= min_speed) & df["steer"].notna() & df["yaw"].notna()
    if m.sum() < MIN_CALIBRATION_SAMPLES or df.loc[m, "steer"].nunique() < 2:
        return 1.0, 0.0
    slope = np.polyfit(df.loc[m, "steer"], df.loc[m, "yaw"], 1)[0]
    return (1.0 if slope >= 0 else -1.0), abs(slope)


def find_runs(session: Session, p: DetectParams) -> List[Run]:
    df, hz = session.df, session.hz
    sign, scale = calibrate(session, p.min_speed)
    if scale == 0.0:
        return []   # no driving above min_speed, so there's nothing to judge
    win = max(1, int(p.smooth * hz))
    steer = sign * df["steer"].rolling(win, center=True, min_periods=1).mean()
    yaw = df["yaw"].rolling(win, center=True, min_periods=1).mean()

    mask = ((df["speed"] >= p.min_speed) & (steer.abs() >= p.min_steer)
            & (yaw.abs() >= p.min_yaw) & (np.sign(steer) != np.sign(yaw))).to_numpy()

    # contiguous runs of True, then merge runs separated by < merge_gap
    edges = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    runs = list(zip(np.where(edges == 1)[0], np.where(edges == -1)[0]))
    merged: List[Tuple[int, int]] = []
    for s, e in runs:
        if merged and (s - merged[-1][1]) / hz < p.merge_gap:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))

    out = []
    for s, e in merged:
        dur = (df["t"].iloc[e - 1] - df["t"].iloc[s]) + 1 / hz
        if dur < p.min_duration:
            continue
        seg = slice(s, e)
        mismatch = yaw.iloc[seg].abs()
        out.append(Run(
            start=int(s), end=int(e), duration=float(dur),
            severity=float(dur * mismatch.mean()),
            details={"peak_steer_deg": round(float(steer.iloc[seg].abs().max()), 1),
                     "peak_yaw_dps": round(float(mismatch.max()), 1)}))
    return out
