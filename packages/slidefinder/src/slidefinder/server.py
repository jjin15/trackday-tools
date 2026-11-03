"""Local web app: upload a session, tune detection, line slides up with video clips."""
from __future__ import annotations

import shutil
import tempfile
import threading
import uuid
import webbrowser
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Optional

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from racelog import loader
from racelog.start import detect_start
from racelog.tracks import (TrackError, TrackInfo, add_user_track, find_crossings, list_tracks,
                            load_gates, match_session_track)

from . import __version__
from .detect.auto import DetectionUnavailable, detect
from .presets import DEFAULT_PRESET, PARAM_INFO, PRESETS
from .report import build_events, rank_events
from .sync import parse_clip_lengths, solve_offset

WEB_DIR = Path(__file__).parent / "web"
DEFAULT_CLIP_LENGTH = "12:48"


class Record:
    """One uploaded session and everything derived from it."""

    def __init__(self, sid: str, filename: str, path: Path):
        self.id = sid
        self.filename = filename
        self.path = path
        self.format = loader.format_of(path)
        self.parts = loader.list_parts(path)
        self.lock = threading.Lock()
        self.select_part(loader.default_part(path))

    def select_part(self, part: int) -> None:
        """(Re)load the session for one part of the file and forget anything derived from the last."""
        self.part = part
        self.session = loader.load_session(self.path, part=part)
        self.t_start = detect_start(self.session)
        self.set_track(loader.embedded_track(self.path) or match_session_track(self.session.track_name))

    def set_track(self, track: Optional[TrackInfo]) -> None:
        self.track = track
        self.gates = load_gates(track.path) if track else None
        self.crossings = find_crossings(self.session, self.gates) if self.gates else None

    def summary(self) -> dict:
        s = self.session
        lap_numbers = s.df["lap_number"].dropna().unique()
        return {
            "id": self.id,
            "filename": self.filename,
            "format": self.format,
            "parts": [asdict(p) for p in self.parts],
            "part": self.part,
            "track_name": s.track_name,
            "track": {"name": self.track.name} if self.track else None,
            "laps": int(len(lap_numbers)),
            "lap_range": [int(lap_numbers.min()), int(lap_numbers.max())] if len(lap_numbers) else None,
            "duration_s": round(s.duration, 1),
            "t_start_s": round(self.t_start, 2),
            "has_steering": s.has_steering,
            "has_slip_inputs": s.has_slip_inputs,
        }


class SyncRequest(BaseModel):
    session_time_s: float
    clip_lengths: str = DEFAULT_CLIP_LENGTH
    clip: int
    clip_time: str


def _clean(value):
    """Make numpy scalars and NaNs JSON safe."""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if np.isnan(value) else float(value)
    return value


def create_app() -> FastAPI:
    workdir = Path(tempfile.mkdtemp(prefix="slidefinder-"))
    records: Dict[str, Record] = {}

    @asynccontextmanager
    async def lifespan(_app):
        yield
        shutil.rmtree(workdir, ignore_errors=True)   # uploaded sessions don't outlive the server

    app = FastAPI(title="SlideFinder", version=__version__, lifespan=lifespan)

    def get(sid: str) -> Record:
        if sid not in records:
            raise HTTPException(404, "That session isn't loaded any more. Upload the file again.")
        return records[sid]

    @app.get("/api/config")
    def config() -> dict:
        return {
            "version": __version__,
            "default_preset": DEFAULT_PRESET,
            "default_clip_length": DEFAULT_CLIP_LENGTH,
            "presets": {k: {"label": v.label, "summary": v.summary, "steering": asdict(v.params),
                            "slip": asdict(v.slip)} for k, v in PRESETS.items()},
            "params": [asdict(p) for p in PARAM_INFO],
            "tracks": [t.name for t in list_tracks()],
        }

    @app.post("/api/sessions")
    def upload_session(file: UploadFile = File(...)) -> dict:
        sid = uuid.uuid4().hex[:12]
        path = workdir / f"{sid}.csv"
        with open(path, "wb") as out:
            shutil.copyfileobj(file.file, out, length=1024 * 1024)
        try:
            records[sid] = Record(sid, file.filename or "session", path)
        except loader.FormatError as err:
            path.unlink(missing_ok=True)
            raise HTTPException(422, str(err))
        return records[sid].summary()

    @app.get("/api/sessions/{sid}")
    def session_summary(sid: str) -> dict:
        return get(sid).summary()

    @app.delete("/api/sessions/{sid}")
    def delete_session(sid: str) -> dict:
        rec = records.pop(sid, None)
        if rec:
            rec.path.unlink(missing_ok=True)
        return {"ok": True}

    @app.post("/api/sessions/{sid}/part/{part}")
    def choose_part(sid: str, part: int) -> dict:
        rec = get(sid)
        if not 0 <= part < len(rec.parts):
            raise HTTPException(422, "That part doesn't exist in this file.")
        with rec.lock:
            try:
                rec.select_part(part)
            except loader.FormatError as err:
                raise HTTPException(422, str(err))
        return rec.summary()

    @app.post("/api/sessions/{sid}/track")
    def upload_track(sid: str, file: UploadFile = File(...)) -> dict:
        rec = get(sid)
        tmp = workdir / f"{uuid.uuid4().hex[:8]}.rcz"
        with open(tmp, "wb") as out:
            shutil.copyfileobj(file.file, out)
        try:
            track = add_user_track(tmp)
        except TrackError as err:
            raise HTTPException(422, str(err))
        finally:
            tmp.unlink(missing_ok=True)
        rec.set_track(track)
        return rec.summary()

    @app.get("/api/sessions/{sid}/slides")
    def slides(sid: str, preset: str = DEFAULT_PRESET, method: str = "auto",
               min_duration: Optional[float] = None, min_steer: Optional[float] = None,
               min_yaw: Optional[float] = None, min_speed: Optional[float] = None,
               min_slip: Optional[float] = None, offset: float = 0.0,
               clip_lengths: str = DEFAULT_CLIP_LENGTH, t_start: Optional[float] = None) -> dict:
        rec = get(sid)
        if preset not in PRESETS:
            raise HTTPException(422, f"Unknown sensitivity '{preset}'.")
        try:
            lengths = parse_clip_lengths(clip_lengths) if clip_lengths.strip() else None
        except ValueError:
            raise HTTPException(422, "Clip lengths should look like 12:48 or 12:48,12:47.")
        try:
            detection = detect(rec.session, preset, method, min_duration=min_duration,
                               min_steer=min_steer, min_yaw=min_yaw, min_speed=min_speed,
                               min_slip=min_slip)
        except DetectionUnavailable as err:
            raise HTTPException(422, str(err))
        t_zero = rec.t_start if t_start is None else t_start
        events = build_events(rec.session, detection.runs, gates=rec.gates, t_zero=t_zero,
                              offset=offset, clip_lengths=lengths, crossings_cache=rec.crossings)
        rows = []
        if not events.empty:
            events = rank_events(events, "severity")
            for row in events.to_dict(orient="records"):
                row = {k: _clean(v) for k, v in row.items()}
                row["id"] = round(row["session_time_s"] + t_zero, 2)   # stable while t_zero or offset change
                rows.append(row)
        return {"method": detection.method, "note": detection.note, "t_zero": round(t_zero, 2),
                "count": len(rows), "events": rows}

    @app.post("/api/sync/solve")
    def solve(req: SyncRequest) -> dict:
        try:
            lengths = parse_clip_lengths(req.clip_lengths)
            mins, _, secs = req.clip_time.strip().rpartition(":")
            clip_time = (float(mins) * 60 if mins else 0.0) + float(secs)
            return {"offset": round(solve_offset(req.session_time_s, lengths, req.clip, clip_time), 2)}
        except ValueError as err:
            raise HTTPException(422, str(err) or "Check the clip number and time.")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    return app


def serve(port: int = 8765, open_browser: bool = True) -> None:
    import uvicorn

    url = f"http://127.0.0.1:{port}/"
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"SlideFinder is running at {url}  (Ctrl+C to stop)")
    print("Everything stays on this computer.")
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")
