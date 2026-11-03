"""Detect slides without a steering angle, from how sideways the car is.

Slip angle is the difference between where the car points (heading, integrated from the
gyro yaw rate) and where it is travelling (GPS course). Heading drifts, so it is re-anchored
to the GPS course on straights, where the car isn't turning and slip is near zero.

Known blind spot: a slip held steady for over a second with almost no yaw rate looks like a
straight, so the heading gets re-anchored inside it and the slide is under-reported. Slides
in corners, where the car keeps rotating, are unaffected. Rejecting such anchors was tried
and made agreement with the steering detector worse on real data.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from ..presets import SlipParams
from racelog.session import Session
from . import Run

ANCHOR_SPEED = 15.0      # m/s; straights below this aren't trusted as anchors
ANCHOR_YAW = 3.0         # deg/s; "not turning"
ANCHOR_SECONDS = 1.0     # how long the car must stay straight to anchor
SIGN_SPEED = 15.0
IMU_AXES = ["ax", "ay", "az", "gx", "gy", "gz"]
IMU_MIN_COVERAGE = 0.9   # fraction of samples with a reading; a few gaps at the start are normal


def _wrap(angle):
    return (angle + 180.0) % 360.0 - 180.0


def imu_yaw_rate(session: Session) -> np.ndarray:
    """Yaw rate about the vertical axis (deg/s).

    With a full IMU the gyro is projected onto the direction of gravity, so it doesn't
    matter how the logger is mounted. Otherwise the logged z gyro axis is used.
    """
    df = session.df
    if df[IMU_AXES].notna().mean().min() >= IMU_MIN_COVERAGE:
        gravity = np.array([df["ax"].median(), df["ay"].median(), df["az"].median()])
        gravity /= np.linalg.norm(gravity)
        return (df["gx"] * gravity[0] + df["gy"] * gravity[1] + df["gz"] * gravity[2]).to_numpy()
    return df["yaw"].to_numpy()


def estimate_slip(session: Session, smooth: float = 0.2) -> Optional[np.ndarray]:
    """Slip angle in degrees at every sample, or None if it can't be estimated."""
    if not session.has_slip_inputs:
        return None
    df, hz = session.df, session.hz
    yaw = np.nan_to_num(imu_yaw_rate(session))
    course = df["bearing"].ffill().bfill().to_numpy()
    speed = df["speed"].ffill().bfill().to_numpy()

    # which way the gyro counts: course rate and yaw rate must agree while driving
    course_rate = np.gradient(np.unwrap(np.radians(course))) * hz * 180.0 / np.pi
    moving = speed > SIGN_SPEED
    if moving.sum() < hz or np.std(yaw[moving]) == 0 or np.std(course_rate[moving]) == 0:
        return None
    sign = 1.0 if np.corrcoef(course_rate[moving], yaw[moving])[0, 1] >= 0 else -1.0

    heading = np.cumsum(sign * yaw) / hz
    straight = (np.abs(yaw) < ANCHOR_YAW) & (speed > ANCHOR_SPEED)
    straight = pd.Series(straight).rolling(int(ANCHOR_SECONDS * hz), center=True).min().fillna(0).astype(bool)
    anchors = np.where(straight.to_numpy())[0]
    if len(anchors) < 2:
        return None
    offset_at = np.unwrap(np.radians(_wrap(course - heading)[anchors])) * 180.0 / np.pi
    offset = np.interp(np.arange(len(df)), anchors, offset_at)
    slip = _wrap(course - heading - offset)
    win = max(1, int(smooth * hz))
    return pd.Series(slip).rolling(win, center=True, min_periods=1).mean().to_numpy()


def find_runs(session: Session, p: SlipParams) -> List[Run]:
    slip = estimate_slip(session, p.smooth)
    if slip is None:
        return []
    df, hz = session.df, session.hz
    mask = ((np.abs(slip) >= p.min_slip) & (df["speed"].to_numpy() >= p.min_speed))

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
        seg = np.abs(slip[s:e])
        out.append(Run(start=int(s), end=int(e), duration=float(dur),
                       severity=float(dur * seg.mean()),
                       details={"peak_slip_deg": round(float(seg.max()), 1)}))
    return out
