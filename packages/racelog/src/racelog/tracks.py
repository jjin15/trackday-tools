"""RaceChrono track files (.rcz): the registry, their gates, and sectors."""
from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .session import Session

BUNDLED_DIR = Path(__file__).parent / "data" / "tracks"
USER_DIR = Path.home() / ".racelog" / "tracks"
LEGACY_USER_DIR = Path.home() / ".slidefinder" / "tracks"     # where SlideFinder used to keep them


class TrackError(ValueError):
    """The file isn't a usable RaceChrono track."""


@dataclass
class TrackInfo:
    name: str    # the name RaceChrono shows, which sessions also record in their header
    path: Path


def read_track_json(path) -> dict:
    """The `track` object inside an .rcz, checked for the parts this tool relies on."""
    try:
        with zipfile.ZipFile(path) as z:
            track = json.loads(z.read("trackId.json"))["track"]
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as err:
        raise TrackError("That doesn't look like a RaceChrono track file (.rcz).") from err
    gates = track.get("traps") or []
    if not track.get("name") or not gates:
        raise TrackError("That track file has no name or no checkpoints, so sectors can't be made.")
    if not any(g.get("type") == 3 for g in gates):
        raise TrackError("That track file has no start/finish line, so sectors can't be ordered.")
    return track


def add_user_track(path) -> "TrackInfo":
    """Check an .rcz and copy it into the user's track folder so later sessions find it."""
    name = read_track_json(path)["name"]
    USER_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.lower()).strip("_") or "track"
    dest = USER_DIR / f"{safe}.rcz"
    dest.write_bytes(Path(path).read_bytes())
    return TrackInfo(name, dest)


def load_gates(path) -> List[Dict]:
    """Read gates from a RaceChrono .rcz (a zip holding trackId.json) without extracting it.

    Coordinates are stored in 1/100000 arc-minute, bearing in 1/1000 deg, width in mm.
    """
    return [{"name": g["name"], "type": g["type"],
             "lat": g["centerLatitude"] / 6e6, "lon": g["centerLongitude"] / 6e6,
             "bearing": g["bearing"] / 1000.0, "half_width": g["width"] / 2000.0}
            for g in read_track_json(path)["traps"]]


def list_tracks() -> List[TrackInfo]:
    """Every known track: bundled ones, then any the user added under ~/.racelog/tracks
    (or the old ~/.slidefinder/tracks)."""
    found = []
    for folder in (BUNDLED_DIR, USER_DIR, LEGACY_USER_DIR):
        for path in sorted(folder.glob("*.rcz")) if folder.exists() else []:
            try:
                found.append(TrackInfo(read_track_json(path)["name"], path))
            except TrackError:
                continue   # not a usable track file
    return found


def match_session_track(name: str) -> Optional[TrackInfo]:
    """The known track whose name equals the one recorded in a session header."""
    name = name.strip().lower()
    return next((t for t in list_tracks() if t.name.strip().lower() == name), None) if name else None


def find_track(query: str) -> TrackInfo:
    """Resolve a user-typed track: a path to an .rcz, or part of a known track's name."""
    if query.lower().endswith(".rcz") and Path(query).exists():
        return TrackInfo(read_track_json(query)["name"], Path(query))
    tracks = list_tracks()
    hits = [t for t in tracks if query.lower() in t.name.lower() or query.lower() in t.path.stem.lower()]
    if len(hits) == 1:
        return hits[0]
    known = ", ".join(t.name for t in tracks) or "none"
    if not hits:
        raise LookupError(f"No track matches '{query}'. Known tracks: {known}")
    raise LookupError(f"'{query}' matches several tracks ({', '.join(t.name for t in hits)}); be more specific.")


def find_crossings(session: Session, gates: List[Dict]) -> Tuple[List[Tuple[float, str]], List[str]]:
    """Return [(t, gate_name)] sorted by time and the gate names in lap order.

    A crossing is the path passing through the gate line in the gate's bearing
    direction, within its width. Lap order starts at the start/finish gate (type 3).
    """
    df = session.df
    lat0, lon0 = df["latitude"].mean(), df["longitude"].mean()
    kx = 111320.0 * np.cos(np.radians(lat0))
    ky = 111320.0
    x = ((df["longitude"] - lon0) * kx).to_numpy()
    y = ((df["latitude"] - lat0) * ky).to_numpy()
    t = df["t"].to_numpy()
    crossings = []
    for g in gates:
        b = np.radians(g["bearing"])
        dx, dy = np.sin(b), np.cos(b)
        gx, gy = (g["lon"] - lon0) * kx, (g["lat"] - lat0) * ky
        u = (x - gx) * dx + (y - gy) * dy
        v = (x - gx) * dy - (y - gy) * dx
        for i in np.where((u[:-1] < 0) & (u[1:] >= 0))[0]:
            if abs(v[i]) <= g["half_width"]:
                frac = -u[i] / (u[i + 1] - u[i])
                crossings.append((t[i] + frac * (t[i + 1] - t[i]), g["name"]))
    crossings.sort()
    start = next(g["name"] for g in gates if g["type"] == 3)
    offsets: Dict[str, List[float]] = {}
    last_start = None
    for ct, name in crossings:
        if name == start:
            last_start = ct
        elif last_start is not None:
            offsets.setdefault(name, []).append(ct - last_start)
    order = [start] + sorted(offsets, key=lambda n: np.median(offsets[n]))
    return crossings, order


def sector_at(crossings, order, t):
    """Sector number (1-based) and 'from->to' label for time t."""
    prev = next(((ct, n) for ct, n in reversed(crossings) if ct <= t), None)
    if prev is None:
        return "", ""
    to = order[(order.index(prev[1]) + 1) % len(order)]
    return order.index(prev[1]) + 1, f"{prev[1]}→{to}"
