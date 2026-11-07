from slidefinder.detect.steering import calibrate, find_runs
from slidefinder.presets import DetectParams
from slidefinder.report import build_events, rank_events


def test_sustained_opposite_lock_is_found(session_factory):
    session = session_factory([(20.0, 1.5)])
    runs = find_runs(session, DetectParams())
    assert len(runs) == 1
    assert abs(session.df["t"].iloc[runs[0].start] - 20.0) < 0.3
    assert 1.2 < runs[0].duration < 1.8


def test_quick_counter_steer_is_ignored(session_factory):
    session = session_factory([(20.0, 0.3)])
    assert find_runs(session, DetectParams()) == []


def test_loosening_min_duration_finds_the_short_one(session_factory):
    session = session_factory([(20.0, 0.3)])
    assert len(find_runs(session, DetectParams(min_duration=0.2))) == 1


def test_slow_driving_is_ignored(session_factory):
    session = session_factory([(20.0, 1.5)], speed=5.0)
    assert find_runs(session, DetectParams()) == []


def test_calibration_sign_and_scale(session_factory):
    sign, scale = calibrate(session_factory([]), 10.0)
    assert sign == 1.0 and abs(scale - 0.25) < 0.01
    flipped = session_factory([])
    flipped.df["steer"] = -flipped.df["steer"]
    assert calibrate(flipped, 10.0)[0] == -1.0


def test_flipped_steering_gives_same_slides(session_factory):
    session = session_factory([(20.0, 1.5), (40.0, 2.0)])
    session.df["steer"] = -session.df["steer"]
    assert len(find_runs(session, DetectParams())) == 2


def test_events_are_ranked_by_severity(session_factory):
    session = session_factory([(10.0, 1.0), (30.0, 3.0)])
    events = rank_events(build_events(session, find_runs(session, DetectParams())))
    assert list(events["rank"]) == [1, 2]
    assert events["severity"].iloc[0] > events["severity"].iloc[1]
    assert events["duration_s"].iloc[0] > events["duration_s"].iloc[1]


def test_video_columns_follow_offset_and_start(session_factory):
    session = session_factory([(100.0 - 60.0, 1.5)], seconds=60)   # slide at t=40 s
    runs = find_runs(session, DetectParams())
    events = build_events(session, runs, t_zero=10.0, offset=5.0, clip_lengths=[30.0])
    # 40 - 10 (start) + 5 (offset) = 35 s on the video -> clip 2, 5 s in
    assert events["clip"].iloc[0] == 2
    mins, secs = events["clip_time"].iloc[0].split(":")
    assert abs(int(mins) * 60 + float(secs) - 5.0) < 0.1


def test_presets_get_looser(session_factory):
    from slidefinder.presets import PRESETS

    # opposite-lock events lasting 0.4 s, 0.6 s and 1.0 s
    session = session_factory([(10.0, 0.4), (20.0, 0.6), (30.0, 1.0)])
    counts = {name: len(find_runs(session, p.params)) for name, p in PRESETS.items()}
    assert counts == {"strict": 1, "balanced": 2, "loose": 3}


def test_turn_column_names_the_turn_the_slide_is_in(session_factory, tmp_path):
    import json

    import numpy as np
    from racelog.turns import build_turn_map, read_turns

    session = session_factory([(40.0, 1.5)], seconds=60)    # synthetic path runs north at 1.11 m/s
    dist = np.linspace(0.0, 70.0, 71)
    data = build_turn_map("Synthetic Track", 38.0 + dist / 111320.0, np.full_like(dist, -122.0), dist,
                          [{"name": "T1", "from_m": 10, "to_m": 20}, {"name": "T2", "from_m": 40, "to_m": 50}])
    (tmp_path / "turns.json").write_text(json.dumps(data))
    events = build_events(session, find_runs(session, DetectParams()), turn_map=read_turns(tmp_path / "turns.json"))
    assert list(events["turn"]) == ["T2"]
    assert "turn" not in build_events(session, find_runs(session, DetectParams())).columns
