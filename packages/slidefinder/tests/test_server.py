import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from racelog import tracks
from racelog.testing import write_racechrono_csv
from slidefinder.server import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def uploaded(client, session_factory, tmp_path):
    """A session with two slides (1.0 s and 3.0 s) uploaded through the API."""
    path = tmp_path / "s.csv"
    write_racechrono_csv(session_factory([(10.0, 1.0), (30.0, 3.0)]), path, track="Nowhere Raceway")
    with open(path, "rb") as fh:
        res = client.post("/api/sessions", files={"file": ("s.csv", fh, "text/csv")})
    assert res.status_code == 200, res.text
    return client, res.json()


def test_config_describes_presets_and_params(client):
    cfg = client.get("/api/config").json()
    assert list(cfg["presets"]) == ["strict", "balanced", "loose"]
    assert cfg["presets"]["strict"]["steering"]["min_duration"] == 0.75
    assert {p["key"] for p in cfg["params"]} == {"min_duration", "min_steer", "min_yaw",
                                                  "min_slip", "min_speed"}
    slip_only = [p["key"] for p in cfg["params"] if p["methods"] == ["slip"]]
    assert slip_only == ["min_slip"]


def test_upload_summary(uploaded):
    _, info = uploaded
    assert info["filename"] == "s.csv" and info["has_steering"] and info["has_slip_inputs"]
    assert info["track_name"] == "Nowhere Raceway" and info["track"] is None


def test_slides_ranked_and_sensitivity_changes_the_count(uploaded):
    client, info = uploaded
    strict = client.get(f"/api/sessions/{info['id']}/slides?preset=strict").json()
    assert strict["method"] == "steering" and strict["count"] == 2
    assert [e["rank"] for e in strict["events"]] == [1, 2]
    assert strict["events"][0]["duration_s"] > strict["events"][1]["duration_s"]
    # raising the minimum duration above the shorter slide drops it
    custom = client.get(f"/api/sessions/{info['id']}/slides?preset=strict&min_duration=2").json()
    assert custom["count"] == 1


def test_slides_clip_and_offset(uploaded):
    client, info = uploaded
    url = f"/api/sessions/{info['id']}/slides?clip_lengths=0:20&t_start=0&offset=0"
    events = client.get(url).json()["events"]
    by_time = {round(e["session_time_s"]): e for e in events}
    assert by_time[10]["clip"] == 1 and by_time[30]["clip"] == 2      # 30 s -> clip 2, 10 s in
    shifted = client.get(url + "&offset=-15").json()["events"]
    assert {round(e["session_time_s"]) for e in shifted} == {10, 30}
    assert min(e["video_time"] for e in shifted).startswith("-")      # 10 s - 15 s is before the video


def test_event_ids_stay_put_when_the_offset_changes(uploaded):
    client, info = uploaded
    a = client.get(f"/api/sessions/{info['id']}/slides?offset=0").json()["events"]
    b = client.get(f"/api/sessions/{info['id']}/slides?offset=7&t_start=0").json()["events"]
    assert {e["id"] for e in a} == {e["id"] for e in b}


def test_bad_inputs_are_rejected_with_messages(uploaded, client):
    _, info = uploaded
    assert client.get(f"/api/sessions/{info['id']}/slides?preset=wild").status_code == 422
    bad = client.get(f"/api/sessions/{info['id']}/slides?clip_lengths=abc")
    assert bad.status_code == 422 and "12:48" in bad.json()["detail"]
    assert client.get("/api/sessions/nope/slides").status_code == 404
    garbage = client.post("/api/sessions", files={"file": ("x.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")})
    assert garbage.status_code == 422 and "RaceChrono" in garbage.json()["detail"]


def test_sync_solver_endpoint(client):
    ok = client.post("/api/sync/solve", json={"session_time_s": 860, "clip_lengths": "12:48,12:30",
                                              "clip": 2, "clip_time": "02:00"})
    assert ok.json() == {"offset": 768 + 120 - 860}
    bad = client.post("/api/sync/solve", json={"session_time_s": 1, "clip": 0, "clip_time": "00:10"})
    assert bad.status_code == 422


def test_uploading_a_track_enables_sectors(uploaded, tmp_path, monkeypatch):
    client, info = uploaded
    monkeypatch.setattr(tracks, "USER_DIR", tmp_path / "user_tracks")
    gate = {"name": "S/F", "centerLatitude": int(38.0003 * 6e6), "centerLongitude": int(-122.0 * 6e6),
            "bearing": 0, "width": 100000, "type": 3}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("trackId.json", json.dumps({"track": {"name": "Nowhere Raceway", "traps": [gate]}}))
    res = client.post(f"/api/sessions/{info['id']}/track", files={"file": ("t.rcz", buf.getvalue())})
    assert res.status_code == 200 and res.json()["track"]["name"] == "Nowhere Raceway"
    events = client.get(f"/api/sessions/{info['id']}/slides").json()["events"]
    assert "sector" in events[0]
    bad = client.post(f"/api/sessions/{info['id']}/track", files={"file": ("t.rcz", b"not a zip")})
    assert bad.status_code == 422


def test_deleting_a_session(uploaded):
    client, info = uploaded
    assert client.delete(f"/api/sessions/{info['id']}").json() == {"ok": True}
    assert client.get(f"/api/sessions/{info['id']}/slides").status_code == 404


@pytest.fixture
def uploaded_rcz(client, session_factory, tmp_path):
    import dataclasses

    from racelog.testing import GATE_SF, write_racechrono_rcz

    first = session_factory([])
    second = dataclasses.replace(session_factory([(30.0, 3.0)]), t0=first.t0 + 6 * 3600)
    path = tmp_path / "s.rcz"
    write_racechrono_rcz(path, [first, second], [[(1, 0.0, None)], [(2, 0.0, 30.0), (3, 30.0, None)]],
                         track_name="Nowhere Raceway", embedded_track=[GATE_SF])
    with open(path, "rb") as fh:
        res = client.post("/api/sessions", files={"file": ("s.rcz", fh, "application/octet-stream")})
    assert res.status_code == 200, res.text
    return client, res.json()


def test_rcz_upload_summary_lists_parts_and_uses_the_embedded_track(uploaded_rcz):
    _, info = uploaded_rcz
    assert info["format"] == "rcz" and info["part"] == 1
    assert [p["laps"] for p in info["parts"]] == [1, 2]
    assert info["parts"][1]["label"].startswith("Part 2")
    assert info["track"] == {"name": "Nowhere Raceway"}          # came from inside the file
    assert info["lap_range"] == [2, 3]


def test_rcz_slides_and_switching_parts(uploaded_rcz):
    client, info = uploaded_rcz
    sid = info["id"]
    slides = client.get(f"/api/sessions/{sid}/slides").json()
    assert slides["count"] == 1 and "sector" in slides["events"][0]
    other = client.post(f"/api/sessions/{sid}/part/0").json()
    assert other["part"] == 0 and other["lap_range"] == [1, 1]
    assert client.get(f"/api/sessions/{sid}/slides").json()["count"] == 0
    client.post(f"/api/sessions/{sid}/part/1")
    assert client.get(f"/api/sessions/{sid}/slides").json()["count"] == 1
    assert client.post(f"/api/sessions/{sid}/part/5").status_code == 422
    assert client.post("/api/sessions/nope/part/0").status_code == 404


def test_a_track_file_uploaded_as_a_session_is_refused_clearly(client):
    import json as _json
    import zipfile as _zip

    buf = io.BytesIO()
    with _zip.ZipFile(buf, "w") as z:
        z.writestr("trackId.json", _json.dumps({"track": {"name": "X", "traps": []}}))
    res = client.post("/api/sessions", files={"file": ("track.rcz", buf.getvalue())})
    assert res.status_code == 422 and "track file, not a session" in res.json()["detail"]


def test_slides_carry_ids_that_other_tools_can_match_on(uploaded_rcz):
    client, info = uploaded_rcz
    events = client.get(f"/api/sessions/{info['id']}/slides").json()["events"]
    e = events[0]
    assert len(e["session_id"]) == 12 and e["source_lap"] in (2, 3)    # RaceChrono's own lap number
    assert e["session_start"] > 1_700_000_000
    # the display lap restarts at 1 within the part; the source lap does not
    assert e["lap"] == e["source_lap"] - 1


def test_the_lap_viewer_no_longer_lives_here(uploaded):
    client, info = uploaded
    assert client.get(f"/api/sessions/{info['id']}/laps").status_code in (404, 405)
    assert client.get("/static/plotly.min.js").status_code == 404
