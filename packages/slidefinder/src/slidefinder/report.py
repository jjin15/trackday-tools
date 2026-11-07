"""Turn detected runs into the table people read: laps, sectors, video clip and time."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .detect import Run
from racelog.session import Session
from racelog.tracks import find_crossings, sector_at
from racelog.turns import TurnMap
from racelog.util import fmt_time
from .sync import locate_clip

MPH_PER_MS = 2.23694


def build_events(session: Session, runs: List[Run], gates: Optional[List[Dict]] = None,
                 t_zero: float = 0.0, offset: float = 0.0,
                 clip_lengths: Optional[List[float]] = None,
                 relabel_laps: bool = True, crossings_cache=None,
                 turn_map: Optional[TurnMap] = None) -> pd.DataFrame:
    """Describe each run. Times are measured from t_zero; video time adds `offset`.

    `crossings_cache` is the (crossings, order) pair from tracks.find_crossings, to avoid
    recomputing it when the same session is analysed repeatedly. `turn_map` adds a `turn`
    column ("T7", "after T7").
    """
    df = session.df
    lap_base = df["lap_number"].min() - 1 if relabel_laps else 0
    crossings, order = (crossings_cache or find_crossings(session, gates)) if gates else ([], [])
    events = []
    for r in runs:
        s, e = r.start, r.end
        lap = df["lap_number"].iloc[s]
        lap_start = df.loc[df["lap_number"] == lap, "t"].min() if pd.notna(lap) else np.nan
        start_t = df["t"].iloc[s]
        sector, sector_name = sector_at(crossings, order, start_t) if gates else ("", "")
        video_t = start_t - t_zero + offset
        clip, clip_time = locate_clip(video_t, clip_lengths) if clip_lengths else ("", "")
        events.append({
            "lap": int(lap - lap_base) if pd.notna(lap) else "",
            # placed at the middle of the slide, so one that starts just before a turn still names that turn
            **({"turn": turn_map.labels(df["latitude"].iloc[(s + e) // 2],
                                        df["longitude"].iloc[(s + e) // 2])[0]} if turn_map else {}),
            **({"sector": sector, "sector_name": sector_name} if gates else {}),
            "time_in_lap_s": round(start_t - lap_start, 2) if pd.notna(lap) else "",
            "session_time": fmt_time(start_t - t_zero),
            "session_time_s": round(start_t - t_zero, 2),
            "video_time": fmt_time(video_t),
            **({"clip": clip, "clip_time": clip_time} if clip_lengths else {}),
            "wall_clock_utc": datetime.fromtimestamp(session.t0 + start_t, timezone.utc)
                                      .strftime("%H:%M:%S"),
            "duration_s": round(r.duration, 2),
            **r.details,
            "min_speed_mph": round(float(df["speed"].iloc[s:e].min()) * MPH_PER_MS, 1),
            "lat": round(float(df["latitude"].iloc[s]), 6),
            "lon": round(float(df["longitude"].iloc[s]), 6),
            "severity": round(r.severity, 1),
            # these let another tool put the slide back on the right lap of the right session
            "session_id": session.fingerprint,
            "session_start": round(session.t0, 3),
            "source_lap": int(lap) if pd.notna(lap) else "",
        })
    return pd.DataFrame(events)


def rank_events(events: pd.DataFrame, sort: str = "severity") -> pd.DataFrame:
    """Add a `rank` column (1 = most severe) and order by severity or time."""
    if events.empty:
        return events
    if sort == "severity":
        events = events.sort_values("severity", ascending=False)
    events = events.copy()
    events.insert(0, "rank", events["severity"].rank(ascending=False, method="first").astype(int))
    return events
