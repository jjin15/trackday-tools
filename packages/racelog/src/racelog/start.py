"""Work out when the car actually starts driving on track."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .session import Session


def detect_start(session: Session, pit_speed: float = 5.0, fast_speed: float = 20.0,
                 sustain: float = 2.0) -> float:
    """Time (s from first sample) when the car leaves the pits and starts driving on track.

    Finds the first point where GPS speed stays >= fast_speed for `sustain` seconds, then
    backs up to the last moment before that when the car was below pit_speed (the pit exit
    launch or the end of the pit lane crawl).
    """
    df = session.df
    speed = df["speed"].ffill().to_numpy()
    win = max(1, int(sustain * session.hz))
    fast = pd.Series(speed).rolling(win).min().to_numpy() >= fast_speed
    if not fast.any():
        return 0.0
    first_fast = int(np.argmax(fast)) - win + 1
    slow = np.where(speed[:first_fast] < pit_speed)[0]
    return float(df["t"].iloc[slow[-1] + 1] if len(slow) else df["t"].iloc[0])
