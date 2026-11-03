import pytest

from racelog.racechrono import RaceChronoFormatError, load_session, read_header
from racelog.testing import write_racechrono_csv


def test_loader_reads_header_and_prefers_gps_speed(session_factory, tmp_path):
    session = session_factory([(20.0, 1.5)])
    path = tmp_path / "s.csv"
    write_racechrono_csv(session, path)
    header = read_header(path)
    assert header.meta["track name"] == "Synthetic Track"
    assert header.find("speed", "gps").source == "gps"
    loaded = load_session(path)
    assert loaded.has_steering
    assert loaded.df["speed"].median() == pytest.approx(30.0, abs=0.01)   # not the 0.0 decoys


def test_missing_gps_is_a_readable_error(session_factory, tmp_path):
    path = tmp_path / "s.csv"
    write_racechrono_csv(session_factory([]), path, drop=("latitude",))
    with pytest.raises(RaceChronoFormatError, match="missing required channels: latitude"):
        load_session(path)


def test_a_file_that_is_not_racechrono(tmp_path):
    path = tmp_path / "nope.csv"
    path.write_text("a,b,c\n1,2,3\n")
    with pytest.raises(RaceChronoFormatError, match="RaceChrono"):
        load_session(path)


def test_optional_channels_may_be_absent(session_factory, tmp_path):
    path = tmp_path / "s.csv"
    write_racechrono_csv(session_factory([]), path, steering=False)
    s = load_session(path)
    assert not s.has_steering and s.df["steer"].isna().all()
