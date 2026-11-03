"""Local web app: upload a session and compare its laps."""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import uuid
import webbrowser
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import plotly
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from racelog import loader

from . import __version__
from .laps import build_data

WEB_DIR = Path(__file__).parent / "web"
START_TOLERANCE_S = 1.0     # session starts closer than this are the same recording


class Record:
    """One uploaded session."""

    def __init__(self, sid: str, filename: str, path: Path):
        self.id = sid
        self.filename = filename
        self.path = path
        self.format = loader.format_of(path)
        self.parts = loader.list_parts(path)
        self.lock = threading.Lock()
        self.select_part(loader.default_part(path))

    def select_part(self, part: int) -> None:
        self.part = part
        self.session = loader.load_session(self.path, part=part)
        self.laps_json: Optional[bytes] = None

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
            "laps": int(len(lap_numbers)),
            "lap_range": [int(lap_numbers.min()), int(lap_numbers.max())] if len(lap_numbers) else None,
            "duration_s": round(s.duration, 1),
            "session_id": s.fingerprint,
            "session_start": round(s.t0, 3),
        }

    def lap_data(self) -> bytes:
        with self.lock:
            if self.laps_json is None:
                data = build_data(self.path, part=self.part)
                data["session_id"] = self.session.fingerprint
                data["session_start"] = round(self.session.t0, 3)
                self.laps_json = json.dumps(data, separators=(",", ":")).encode()
            return self.laps_json


def match_slides(csv_path, session, laps: List[dict]) -> dict:
    """Pick the slides in a SlideFinder export that belong to this session and place them on laps.

    Returns {"markers": [...], "matched", "skipped", "note"}. Each marker has the lap number
    used on screen (`lap`), the time into that lap, and the slide's rank.
    """
    try:
        df = pd.read_csv(csv_path)
    except Exception:
        raise ValueError("That file couldn't be read as a SlideFinder slides export (CSV).")
    if not {"time_in_lap_s"} <= set(df.columns) or not ({"source_lap", "lap"} & set(df.columns)):
        raise ValueError("That doesn't look like a SlideFinder slides export: it has no lap or time-in-lap columns.")

    note = ""
    if "session_id" in df.columns:
        keep = df["session_id"].astype(str) == session.fingerprint
    elif "session_start" in df.columns:
        keep = (df["session_start"] - session.t0).abs() < START_TOLERANCE_S
    else:
        keep = pd.Series(True, index=df.index)
        note = ("This export has no session id (it is from an older SlideFinder), so it was assumed to belong "
                "to this session and part.")
    matched = df[keep]
    by_source = {l["source"]: l["n"] for l in laps}
    by_display = {l["n"]: l["n"] for l in laps}
    markers = []
    for _, row in matched.iterrows():
        if "source_lap" in df.columns and pd.notna(row["source_lap"]) and row["source_lap"] != "":
            lap = by_source.get(int(row["source_lap"]))
        elif pd.notna(row.get("lap")) and row.get("lap") != "":
            lap = by_display.get(int(row["lap"]))
        else:
            lap = None
        if lap is None or pd.isna(row["time_in_lap_s"]):
            continue
        markers.append({"lap": lap, "time_in_lap_s": float(row["time_in_lap_s"]),
                        "rank": int(row["rank"]) if "rank" in df.columns and pd.notna(row.get("rank")) else None,
                        "label": str(row["sector_name"]) if "sector_name" in df.columns and pd.notna(row.get("sector_name")) else ""})
    if not len(matched):
        note = "None of the slides in that file are from this session. Check that you opened the same session and part."
    return {"markers": markers, "matched": len(markers), "skipped": int(len(df) - len(markers)), "note": note}


def create_app() -> FastAPI:
    workdir = Path(tempfile.mkdtemp(prefix="lapcompare-"))
    records: Dict[str, Record] = {}

    @asynccontextmanager
    async def lifespan(_app):
        yield
        shutil.rmtree(workdir, ignore_errors=True)   # uploaded sessions don't outlive the server

    app = FastAPI(title="Lap Compare", version=__version__, lifespan=lifespan)

    def get(sid: str) -> Record:
        if sid not in records:
            raise HTTPException(404, "That session isn't loaded any more. Upload the file again.")
        return records[sid]

    @app.get("/api/config")
    def config() -> dict:
        return {"version": __version__}

    @app.post("/api/sessions")
    def upload_session(file: UploadFile = File(...)) -> dict:
        sid = uuid.uuid4().hex[:12]
        path = workdir / f"{sid}.dat"
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

    @app.get("/api/sessions/{sid}/laps")
    def laps(sid: str) -> Response:
        return Response(get(sid).lap_data(), media_type="application/json")

    @app.post("/api/sessions/{sid}/slides")
    def load_slides(sid: str, file: UploadFile = File(...)) -> dict:
        rec = get(sid)
        tmp = workdir / f"{uuid.uuid4().hex[:8]}.csv"
        with open(tmp, "wb") as out:
            shutil.copyfileobj(file.file, out)
        try:
            return match_slides(tmp, rec.session, json.loads(rec.lap_data())["laps"])
        except ValueError as err:
            raise HTTPException(422, str(err))
        finally:
            tmp.unlink(missing_ok=True)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/static/plotly.min.js")
    def plotly_js() -> FileResponse:   # bundled with the plotly package, so the page works offline
        return FileResponse(Path(plotly.__file__).parent / "package_data" / "plotly.min.js",
                            media_type="application/javascript")

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    return app


def serve(port: int = 8766, open_browser: bool = True) -> None:
    import uvicorn

    url = f"http://127.0.0.1:{port}/"
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Lap Compare is running at {url}  (Ctrl+C to stop)")
    print("Everything stays on this computer.")
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")
