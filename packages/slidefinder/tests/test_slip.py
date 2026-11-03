import pytest

from slidefinder.detect.auto import DetectionUnavailable, detect
from slidefinder.detect.slip import estimate_slip, find_runs
from slidefinder.presets import SlipParams


@pytest.mark.parametrize("gyro_sign", [1.0, -1.0])
def test_slide_is_found_whichever_way_the_gyro_counts(slip_session_factory, gyro_sign):
    session = slip_session_factory(gyro_sign=gyro_sign)
    runs = find_runs(session, SlipParams())
    assert len(runs) == 1
    assert abs(session.df["t"].iloc[runs[0].start] - 25.0) < 0.7
    assert 15 < runs[0].details["peak_slip_deg"] < 25


def test_slip_angle_is_near_zero_outside_the_slide(slip_session_factory):
    session = slip_session_factory()
    slip = estimate_slip(session)
    quiet = (session.df["t"] < 20) | (session.df["t"] > 32)
    assert abs(slip[quiet.to_numpy()]).max() < 3.0


def test_small_or_brief_slip_is_ignored(slip_session_factory):
    assert find_runs(slip_session_factory(peak=6.0), SlipParams()) == []
    assert find_runs(slip_session_factory(slide=(25.0, 0.8)), SlipParams()) == []


def test_auto_picks_slip_when_there_is_no_steering(slip_session_factory):
    result = detect(slip_session_factory(), "strict")
    assert result.method == "slip" and len(result.runs) == 1
    assert "slip angle" in result.note


def test_auto_prefers_steering_when_present(session_factory):
    result = detect(session_factory([(20.0, 1.5)]), "strict")
    assert result.method == "steering" and len(result.runs) == 1


def test_forcing_a_missing_method_gives_a_clear_error(session_factory, slip_session_factory):
    with pytest.raises(DetectionUnavailable):
        detect(slip_session_factory(), "strict", method="steering")
    session = session_factory([])
    session.df["bearing"] = float("nan")
    with pytest.raises(DetectionUnavailable):
        detect(session, "strict", method="slip")
