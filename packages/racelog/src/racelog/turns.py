"""Turn maps: which numbered corner a point on track is in.

A turn map is a JSON file holding a reference path (one lap's GPS line, resampled every
`step_m` metres from the start/finish line) and each turn's span along that path. A point
is placed on the track by its nearest path point, so a session's own GPS distance (which
drifts) is never used. Points between turns are labelled "after T7" and so on.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

BUNDLED_DIR = Path(__file__).parent / "data" / "turns"
USER_DIR = Path.home() / ".racelog" / "turns"
MAX_OFF_TRACK_M = 60.0      # farther than this from the reference path (pits, paddock): no label


class TurnMapError(ValueError):
    """The file isn't a usable turn map."""


@dataclass
class Turn:
    name: str
    from_m: float
    to_m: float


@dataclass
class TurnMap:
    track: str              # the track name sessions record, e.g. "Sonoma, more checkpoints"
    lat: np.ndarray
    lon: np.ndarray
    step_m: float
    turns: List[Turn]       # in lap order

    @property
    def length_m(self) -> float:
        return (len(self.lat) - 1) * self.step_m

    def position(self, lat, lon) -> np.ndarray:
        """Metres along the reference lap for each point; NaN if far from the track."""
        lat, lon = np.atleast_1d(np.asarray(lat, float)), np.atleast_1d(np.asarray(lon, float))
        kx = 111320.0 * np.cos(np.radians(self.lat.mean()))
        px, py = self.lon * kx, self.lat * 111320.0
        dx = lon[:, None] * kx - px[None, :]
        dy = lat[:, None] * 111320.0 - py[None, :]
        d2 = dx * dx + dy * dy
        nearest = np.argmin(d2, axis=1)
        s = nearest * self.step_m
        far = (np.sqrt(d2[np.arange(len(lat)), nearest]) > MAX_OFF_TRACK_M) | np.isnan(lat) | np.isnan(lon)
        return np.where(far, np.nan, s)

    def label_at(self, s: float) -> str:
        """'T7' inside a turn, 'after T7' between T7 and the next turn, '' if unknown."""
        if not self.turns or np.isnan(s):
            return ""
        for t in self.turns:
            if t.from_m <= s < t.to_m:
                return t.name
        before = [t for t in self.turns if t.to_m <= s]
        return f"after {(before[-1] if before else self.turns[-1]).name}"

    def labels(self, lat, lon) -> List[str]:
        return [self.label_at(s) for s in self.position(lat, lon)]


def read_turns(path) -> TurnMap:
    try:
        data = json.loads(Path(path).read_text())
        turns = [Turn(t["name"], float(t["from_m"]), float(t["to_m"])) for t in data["turns"]]
        lat, lon = np.array(data["path"], float).T
        tm = TurnMap(data["track"], lat, lon, float(data["step_m"]), turns)
    except (OSError, ValueError, KeyError, TypeError) as err:
        raise TurnMapError(f"{Path(path).name} isn't a usable turn map.") from err
    if len(lat) < 10 or not turns:
        raise TurnMapError(f"{Path(path).name} has no path or no turns.")
    return tm


def list_turn_maps() -> List[TurnMap]:
    """Bundled turn maps, then the user's own in ~/.racelog/turns (a user map wins on a name clash)."""
    found = {}
    for folder in (BUNDLED_DIR, USER_DIR):
        for path in sorted(folder.glob("*.json")) if folder.exists() else []:
            try:
                tm = read_turns(path)
            except TurnMapError:
                continue
            found[tm.track.strip().lower()] = tm
    return list(found.values())


def find_turns(track_name: str) -> Optional[TurnMap]:
    """The turn map for a track name as a session or track file records it."""
    name = (track_name or "").strip().lower()
    return next((tm for tm in list_turn_maps() if tm.track.strip().lower() == name), None) if name else None


def build_turn_map(track: str, lat: Sequence[float], lon: Sequence[float], dist_m: Sequence[float],
                   turns: Sequence[dict], step_m: float = 5.0, note: str = "") -> dict:
    """Make a turn-map dict (write it with json.dump) from one lap's GPS samples.

    `dist_m` is distance from the start/finish line; `turns` are {"name", "from_m", "to_m"}
    in the same distance.
    """
    dist = np.asarray(dist_m, float) - float(dist_m[0])
    grid = np.arange(0.0, dist[-1], step_m)
    path = np.column_stack([np.interp(grid, dist, lat), np.interp(grid, dist, lon)])
    return {"track": track, "step_m": step_m, "note": note,
            "turns": [{"name": t["name"], "from_m": t["from_m"], "to_m": t["to_m"]} for t in turns],
            "path": [[round(a, 7), round(b, 7)] for a, b in path]}
