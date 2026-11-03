import numpy as np
import pandas as pd
import pytest

from racelog import loader, rcz
from racelog.testing import (GATE_SF, write_racechrono_csv, write_racechrono_rcz,
                             write_two_part_rcz)
from slidefinder.cli import main


def test_cli_on_an_rcz_finds_the_slide_in_the_chosen_part(tmp_path, session_factory, capsys):
    path, out = tmp_path / "s.rcz", tmp_path / "out.csv"
    write_two_part_rcz(path)
    assert main([str(path), "--out", str(out), "--no-trim", "--clip-length", "none"]) == 0
    text = capsys.readouterr().out
    assert "2 parts" in text and "Analysing part 2 (most laps)" in text and "1 slides" in text
    # the first part has no slide
    assert main([str(path), "--out", str(out), "--no-trim", "--part", "1"]) == 0
    assert "No slides found" in capsys.readouterr().out
    # part numbers are checked
    assert main([str(path), "--part", "3"]) == 1
    assert "--part must be between 1 and 2" in capsys.readouterr().err


def test_slides_match_the_csv_export_of_the_same_data(tmp_path, session_factory, capsys):
    session = session_factory([(10.0, 1.0), (30.0, 3.0)])
    write_racechrono_rcz(tmp_path / "s.rcz", [session], [[(1, 0.0, None)]])
    write_racechrono_csv(session, tmp_path / "s.csv")
    results = {}
    for name in ("s.rcz", "s.csv"):
        out = tmp_path / f"{name}.out.csv"
        assert main([str(tmp_path / name), "--out", str(out), "--no-trim", "--clip-length", "none"]) == 0
        results[name] = pd.read_csv(out)
    a, b = results["s.rcz"], results["s.csv"]
    assert len(a) == len(b) == 2
    assert np.allclose(a["session_time_s"], b["session_time_s"], atol=0.1)
    assert np.allclose(a["duration_s"], b["duration_s"], atol=0.15)


def test_embedded_track_gives_sectors_without_a_track_file(tmp_path, session_factory, capsys):
    path, out = tmp_path / "s.rcz", tmp_path / "out.csv"
    session = session_factory([(30.0, 3.0)])
    write_racechrono_rcz(path, [session], [[(1, 0.0, None)]], track_name="Nowhere Raceway",
                         embedded_track=[GATE_SF])
    assert loader.embedded_track(path).name == "Nowhere Raceway"
    assert main([str(path), "--out", str(out), "--no-trim"]) == 0
    assert "Track: Nowhere Raceway" in capsys.readouterr().out
    assert "sector" in out.read_text().splitlines()[0]
    # no embedded track and no known track: sectors are skipped with a hint
    bare = tmp_path / "bare.rcz"
    write_racechrono_rcz(bare, [session], [[(1, 0.0, None)]], track_name="Nowhere Raceway")
    assert loader.embedded_track(bare) is None
    assert main([str(bare), "--out", str(out), "--no-trim"]) == 0
    assert "No track file for 'Nowhere Raceway'" in capsys.readouterr().out


def test_without_steering_the_slip_detector_is_used(tmp_path, slip_session_factory, capsys):
    path, out = tmp_path / "s.rcz", tmp_path / "out.csv"
    write_racechrono_rcz(path, [slip_session_factory()], [[(1, 0.0, None)]], steering=False)
    assert not rcz.load_session(path).has_steering
    assert main([str(path), "--out", str(out), "--no-trim"]) == 0
    text = capsys.readouterr().out
    assert "No steering angle in this log" in text and "1 slides" in text


def test_bad_files_give_readable_errors(tmp_path, capsys):
    import json
    import zipfile

    track_only = tmp_path / "track.rcz"
    with zipfile.ZipFile(track_only, "w") as z:
        z.writestr("trackId.json", json.dumps({"track": {"name": "X", "traps": [GATE_SF]}}))
    assert main([str(track_only)]) == 1
    assert "track file, not a session" in capsys.readouterr().err

    broken = tmp_path / "broken.rcz"
    broken.write_bytes(b"PK\x03\x04 not really a zip")
    assert main([str(broken)]) == 1
    assert "valid .rcz" in capsys.readouterr().err
