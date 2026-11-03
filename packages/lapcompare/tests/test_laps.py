import numpy as np
import pytest

from lapcompare import laps as lapdata
from racelog.testing import write_racechrono_rcz, write_two_part_rcz


def test_lap_data_from_an_rcz(tmp_path, session_factory):
    path = tmp_path / "s.rcz"
    write_two_part_rcz(path)
    data = lapdata.build_data(path)                                 # part 2: laps 2 and 3 -> 1 and 2
    assert [l["n"] for l in data["laps"]] == [1, 2]
    assert data["laps"][0]["time"] == pytest.approx(30.0, abs=0.05)
    keys = {s["key"] for s in data["signals"]}
    assert "steering angle" in keys and "z rate of rotation" in keys
    assert "speed (gps)" not in keys          # constant in this synthetic session, so nothing to compare
    first = lapdata.build_data(path, part=0)
    assert [l["n"] for l in first["laps"]] == [1]


def test_every_lap_keeps_ravechrono_original_number(tmp_path, session_factory):
    path = tmp_path / "s.rcz"
    write_two_part_rcz(path)
    data = lapdata.build_data(path)                      # display laps 1, 2 are RaceChrono laps 2, 3
    assert [(l["n"], l["source"]) for l in data["laps"]] == [(1, 2), (2, 3)]


def test_csv_lap_data_matches_rcz_lap_data_for_the_same_session(tmp_path, session_factory):
    from racelog.testing import write_racechrono_csv

    session = session_factory([(30.0, 3.0)])
    session.df.loc[session.df["t"] >= 30.0, "lap_number"] = 2.0       # the CSV takes its laps from here
    laps = [[(1, 0.0, 30.0), (2, 30.0, None)]]
    write_racechrono_rcz(tmp_path / "s.rcz", [session], laps)
    write_racechrono_csv(session, tmp_path / "s.csv")
    a, b = lapdata.build_data(tmp_path / "s.rcz"), lapdata.build_data(tmp_path / "s.csv")
    assert [l["n"] for l in a["laps"]] == [l["n"] for l in b["laps"]] == [1, 2]
    assert [l["source"] for l in a["laps"]] == [l["source"] for l in b["laps"]]
    assert a["step"] == b["step"] == 5.0
