import io

import pytest
from fastapi.testclient import TestClient
from racelog.testing import write_racechrono_csv, write_two_part_rcz

from lapcompare.server import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def uploaded_rcz(client, tmp_path):
    path = tmp_path / "s.rcz"
    write_two_part_rcz(path, track_name="Nowhere Raceway")
    with open(path, "rb") as fh:
        res = client.post("/api/sessions", files={"file": ("s.rcz", fh, "application/octet-stream")})
    assert res.status_code == 200, res.text
    return client, res.json()


def export_csv(rows):
    """A SlideFinder-style slides export with the given rows (dicts)."""
    import pandas as pd

    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    return buf.getvalue().encode()


def test_upload_summary_and_parts(uploaded_rcz):
    _, info = uploaded_rcz
    assert info["format"] == "rcz" and info["part"] == 1 and info["track_name"] == "Nowhere Raceway"
    assert [p["laps"] for p in info["parts"]] == [1, 2] and info["lap_range"] == [2, 3]
    assert len(info["session_id"]) == 12


def test_lap_data_and_switching_parts(uploaded_rcz):
    client, info = uploaded_rcz
    sid = info["id"]
    data = client.get(f"/api/sessions/{sid}/laps").json()
    assert [(l["n"], l["source"]) for l in data["laps"]] == [(1, 2), (2, 3)]
    assert data["session_id"] == info["session_id"]
    other = client.post(f"/api/sessions/{sid}/part/0").json()
    assert other["part"] == 0 and other["session_id"] != info["session_id"]
    assert [l["n"] for l in client.get(f"/api/sessions/{sid}/laps").json()["laps"]] == [1]   # cache not shared
    assert client.post(f"/api/sessions/{sid}/part/5").status_code == 422
    assert client.post("/api/sessions/nope/part/0").status_code == 404


def test_csv_upload_works_too(client, session_factory, tmp_path):
    path = tmp_path / "s.csv"
    write_racechrono_csv(session_factory([]), path)
    with open(path, "rb") as fh:
        res = client.post("/api/sessions", files={"file": ("s.csv", fh, "text/csv")})
    assert res.status_code == 200 and res.json()["format"] == "csv"


def test_bad_uploads_are_refused_with_a_reason(client):
    res = client.post("/api/sessions", files={"file": ("x.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")})
    assert res.status_code == 422 and "RaceChrono" in res.json()["detail"]
    assert client.get("/api/sessions/nope/laps").status_code == 404


def test_slides_are_matched_by_session_id_and_lap(uploaded_rcz):
    client, info = uploaded_rcz
    sid = info["id"]
    rows = [
        {"rank": 1, "lap": 1, "source_lap": 2, "time_in_lap_s": 12.5, "sector_name": "T6→T7",
         "session_id": info["session_id"], "session_start": info["session_start"]},
        {"rank": 2, "lap": 2, "source_lap": 3, "time_in_lap_s": 4.0, "sector_name": "T1–2",
         "session_id": info["session_id"], "session_start": info["session_start"]},
        {"rank": 3, "lap": 1, "source_lap": 2, "time_in_lap_s": 9.0, "sector_name": "",
         "session_id": "someoneelse1", "session_start": 1.0},                 # a different session
        {"rank": 4, "lap": 9, "source_lap": 99, "time_in_lap_s": 3.0, "sector_name": "",
         "session_id": info["session_id"], "session_start": info["session_start"]},   # no such lap
    ]
    res = client.post(f"/api/sessions/{sid}/slides", files={"file": ("slides.csv", export_csv(rows))})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["matched"] == 2 and body["skipped"] == 2
    assert [(m["lap"], m["rank"], m["time_in_lap_s"]) for m in body["markers"]] == [(1, 1, 12.5), (2, 2, 4.0)]


def test_slides_from_another_session_say_so(uploaded_rcz):
    client, info = uploaded_rcz
    rows = [{"rank": 1, "lap": 1, "source_lap": 2, "time_in_lap_s": 5.0, "session_id": "elsewhere123"}]
    res = client.post(f"/api/sessions/{info['id']}/slides", files={"file": ("s.csv", export_csv(rows))}).json()
    assert res["matched"] == 0 and "None of the slides" in res["note"]


def test_matching_falls_back_to_start_time_then_to_lap_numbers(uploaded_rcz):
    client, info = uploaded_rcz
    sid = info["id"]
    by_start = [{"rank": 1, "lap": 1, "source_lap": 2, "time_in_lap_s": 5.0, "session_start": info["session_start"] + 0.2}]
    assert client.post(f"/api/sessions/{sid}/slides", files={"file": ("s.csv", export_csv(by_start))}).json()["matched"] == 1
    legacy = [{"rank": 1, "lap": 2, "time_in_lap_s": 5.0}]                  # an old export: no ids, display laps only
    res = client.post(f"/api/sessions/{sid}/slides", files={"file": ("s.csv", export_csv(legacy))}).json()
    assert res["matched"] == 1 and "no session id" in res["note"]


def test_a_file_that_is_not_a_slides_export_is_refused(uploaded_rcz):
    client, info = uploaded_rcz
    res = client.post(f"/api/sessions/{info['id']}/slides", files={"file": ("x.csv", b"a,b\n1,2\n")})
    assert res.status_code == 422 and "slides export" in res.json()["detail"]


def test_pages_and_assets_are_served(client):
    assert client.get("/").status_code == 200
    for asset in ("app.js", "laps.js", "style.css", "plotly.min.js"):
        assert client.get(f"/static/{asset}").status_code == 200, asset
