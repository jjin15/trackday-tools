import json

import numpy as np
import pytest

from racelog import turns
from racelog.turns import TurnMapError, build_turn_map, find_turns, read_turns

M_PER_DEG = 111320.0


def straight_map(tmp_path, name="Test Track"):
    """A 1 km straight north from (38, -122) with two turns on it."""
    dist = np.linspace(0.0, 1000.0, 201)
    lat, lon = 38.0 + dist / M_PER_DEG, np.full_like(dist, -122.0)
    data = build_turn_map(name, lat, lon, dist, [{"name": "T1", "from_m": 100, "to_m": 200},
                                                  {"name": "T2", "from_m": 500, "to_m": 650}])
    path = tmp_path / "test_track.json"
    path.write_text(json.dumps(data))
    return path


def at(m, east_m=0.0):
    return 38.0 + m / M_PER_DEG, -122.0 + east_m / (M_PER_DEG * np.cos(np.radians(38.0)))


def test_labels_inside_between_and_before_the_first_turn(tmp_path):
    tm = read_turns(straight_map(tmp_path))
    points = [at(150), at(300), at(600), at(900), at(50)]
    lat, lon = zip(*points)
    # before T1 counts as after the last turn of the previous lap
    assert tm.labels(lat, lon) == ["T1", "after T1", "T2", "after T2", "after T2"]


def test_position_ignores_a_few_metres_off_line_but_not_the_paddock(tmp_path):
    tm = read_turns(straight_map(tmp_path))
    s = tm.position(*at(400, east_m=10))
    assert abs(s[0] - 400) <= tm.step_m
    assert np.isnan(tm.position(*at(400, east_m=200))[0])
    assert tm.labels(*at(400, east_m=200)) == [""]


def test_bad_file_raises_a_readable_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{\"track\": \"x\"}")
    with pytest.raises(TurnMapError, match="isn't a usable turn map"):
        read_turns(bad)


def test_find_turns_bundled_and_user_override(tmp_path, monkeypatch):
    sonoma = find_turns("Sonoma, More Checkpoints ")          # case and spaces don't matter
    assert sonoma is not None and [t.name for t in sonoma.turns][:4] == ["T1", "T2", "T3", "T3A"]
    assert find_turns("Laguna Seca v2022") is not None
    assert find_turns("Nowhere") is None and find_turns("") is None

    monkeypatch.setattr(turns, "USER_DIR", tmp_path)
    straight_map(tmp_path, name="Sonoma, more checkpoints")   # the user's own map wins
    assert [t.name for t in find_turns("Sonoma, more checkpoints").turns] == ["T1", "T2"]
