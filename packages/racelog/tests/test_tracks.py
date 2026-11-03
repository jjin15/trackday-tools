import json
import zipfile

import pytest

from racelog import tracks
from racelog.tracks import TrackError, add_user_track, find_track, match_session_track


def make_rcz(path, track):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("trackId.json", json.dumps({"track": track}))
    return path


GATE = {"name": "S/F", "centerLatitude": 228968792, "centerLongitude": -734728684,
        "bearing": 309000, "width": 100000, "type": 3}


@pytest.fixture
def user_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tracks, "USER_DIR", tmp_path / "user_tracks")
    monkeypatch.setattr(tracks, "LEGACY_USER_DIR", tmp_path / "legacy_tracks")
    return tmp_path / "user_tracks"


def test_bundled_sonoma_matches_its_session_header_name():
    track = match_session_track("Sonoma, more checkpoints")
    assert track is not None and track.path.exists()
    assert match_session_track("sonoma, MORE checkpoints ") is not None   # case and spacing
    assert match_session_track("Nowhere Raceway") is None
    assert match_session_track("") is None


def test_find_track_by_partial_name():
    assert "Sonoma" in find_track("sonoma").name
    with pytest.raises(LookupError):
        find_track("nowhere")


def test_gates_are_read_in_real_units():
    gates = tracks.load_gates(find_track("sonoma").path)
    sf = next(g for g in gates if g["type"] == 3)
    assert 38.0 < sf["lat"] < 38.3 and -122.6 < sf["lon"] < -122.3   # Sonoma, CA
    assert 0 <= sf["bearing"] < 360 and sf["half_width"] > 0


def test_adding_a_user_track_makes_it_findable(tmp_path, user_dir):
    rcz = make_rcz(tmp_path / "mine.rcz", {"name": "My Local Track", "traps": [GATE]})
    added = add_user_track(rcz)
    assert added.path.parent == user_dir
    assert match_session_track("my local track").path == added.path


@pytest.mark.parametrize("track, message", [
    ({"traps": [GATE]}, "no name"),
    ({"name": "X", "traps": []}, "no name or no checkpoints"),
    ({"name": "X", "traps": [{**GATE, "type": 4}]}, "no start/finish"),
])
def test_unusable_tracks_are_rejected_with_a_reason(tmp_path, user_dir, track, message):
    with pytest.raises(TrackError, match="track file"):
        add_user_track(make_rcz(tmp_path / "bad.rcz", track))
    assert not user_dir.exists() or not list(user_dir.glob("*.rcz"))


def test_a_non_zip_is_rejected(tmp_path, user_dir):
    bad = tmp_path / "bad.rcz"
    bad.write_text("not a zip")
    with pytest.raises(TrackError):
        add_user_track(bad)


def test_tracks_saved_by_the_old_slidefinder_folder_are_still_found(tmp_path, user_dir):
    legacy = tracks.LEGACY_USER_DIR
    legacy.mkdir(parents=True)
    make_rcz(legacy / "old.rcz", {"name": "Old Circuit", "traps": [GATE]})
    assert match_session_track("old circuit").path == legacy / "old.rcz"
    assert add_user_track(make_rcz(tmp_path / "new.rcz", {"name": "New Circuit", "traps": [GATE]})).path.parent == user_dir
