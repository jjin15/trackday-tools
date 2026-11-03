import dataclasses

from racelog.testing import write_racechrono_csv, write_racechrono_rcz
from racelog import loader


def test_fingerprint_is_short_and_stable(session_factory):
    a, b = session_factory([]), session_factory([(20.0, 1.0)])
    assert len(a.fingerprint) == 12 and a.fingerprint == b.fingerprint   # same recording, same id


def test_fingerprint_changes_with_start_time_and_track(session_factory):
    a = session_factory([])
    later = dataclasses.replace(a, t0=a.t0 + 6 * 3600)
    other_track = dataclasses.replace(a, meta={"track name": "Elsewhere"})
    assert len({a.fingerprint, later.fingerprint, other_track.fingerprint}) == 3


def test_fingerprint_survives_the_analysis_rate(session_factory):
    a = session_factory([])
    assert a.fingerprint == dataclasses.replace(a, hz=25).fingerprint


def test_same_recording_gets_the_same_id_from_csv_and_rcz(session_factory, tmp_path):
    session = session_factory([(30.0, 3.0)])
    write_racechrono_csv(session, tmp_path / "s.csv")
    write_racechrono_rcz(tmp_path / "s.rcz", [session], [[(1, 0.0, None)]])
    assert loader.load_session(tmp_path / "s.csv").fingerprint == loader.load_session(tmp_path / "s.rcz").fingerprint
