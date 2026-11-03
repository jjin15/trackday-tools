"""Open a RaceChrono session from either format: a CSV export or an .rcz archive."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from . import rcz
from .racechrono import RaceChronoFormatError, load_session as _load_csv, read_header
from .session import Session
from .tracks import TrackError, TrackInfo, read_track_json

FormatError = (RaceChronoFormatError, rcz.RczFormatError)


@dataclass
class PartInfo:
    """One selectable stretch of a session. CSV exports are always a single part."""
    index: int
    label: str
    laps: int
    first_lap: Optional[int]
    last_lap: Optional[int]
    minutes: float


def format_of(path) -> str:
    return "rcz" if rcz.is_rcz(path) else "csv"


def list_parts(path) -> List[PartInfo]:
    if format_of(path) == "csv":
        return [PartInfo(0, "Whole file", 0, None, None, 0.0)]
    return [PartInfo(p.index, p.label, len(p.laps), p.laps[0].number if p.laps else None,
                     p.laps[-1].number if p.laps else None, round(p.minutes, 1))
            for p in rcz.list_parts(path)]


def default_part(path) -> int:
    """Index into list_parts() of the part analysed unless asked otherwise."""
    return rcz.default_part(rcz.list_parts(path)) if format_of(path) == "rcz" else 0


def load_session(path, hz: int = 50, part: Optional[int] = None) -> Session:
    """Read a session. `part` indexes list_parts(); ignored for CSV exports."""
    if format_of(path) == "rcz":
        return rcz.load_session(path, hz, part)
    return _load_csv(path, hz)


def embedded_track(path) -> Optional[TrackInfo]:
    """The track stored inside a session .rcz, if it has a usable one."""
    if format_of(path) != "rcz":
        return None
    try:
        return TrackInfo(read_track_json(path)["name"], Path(path))
    except TrackError:
        return None


def track_name(path) -> str:
    """The track the session says it was recorded on."""
    if format_of(path) == "rcz":
        return str(rcz.read_session_meta(path).get("trackName", ""))
    return read_header(path).meta.get("track name", "")
