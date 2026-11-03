from racelog.testing import write_racechrono_csv
from slidefinder.cli import main


def test_cli_end_to_end_with_steering(session_factory, tmp_path, capsys):
    path, out = tmp_path / "s.csv", tmp_path / "out.csv"
    write_racechrono_csv(session_factory([(20.0, 1.5)]), path)
    assert main([str(path), "--out", str(out), "--no-trim", "--clip-length", "none"]) == 0
    text = capsys.readouterr().out
    assert "1 slides" in text and "opposite lock" in text
    assert out.exists()


def test_cli_falls_back_to_slip_without_steering(slip_session_factory, tmp_path, capsys):
    path, out = tmp_path / "s.csv", tmp_path / "out.csv"
    write_racechrono_csv(slip_session_factory(), path, steering=False)
    assert main([str(path), "--out", str(out), "--no-trim"]) == 0
    text = capsys.readouterr().out
    assert "No steering angle in this log" in text
    assert "1 slides" in text


def test_missing_gps_gives_a_readable_error(session_factory, tmp_path, capsys):
    path = tmp_path / "s.csv"
    write_racechrono_csv(session_factory([]), path, drop=("latitude",))
    assert main([str(path)]) == 1
    assert "missing required channels: latitude" in capsys.readouterr().err


def test_not_a_racechrono_file(tmp_path, capsys):
    path = tmp_path / "nope.csv"
    path.write_text("a,b,c\n1,2,3\n")
    assert main([str(path)]) == 1
    assert "RaceChrono" in capsys.readouterr().err


def test_unknown_track_query_lists_known_tracks(session_factory, tmp_path, capsys):
    path = tmp_path / "s.csv"
    write_racechrono_csv(session_factory([]), path)
    assert main([str(path), "--track", "nowhere"]) == 1
    assert "Known tracks" in capsys.readouterr().err


def test_no_steering_and_no_imu_is_a_clear_error(session_factory, tmp_path, capsys):
    path = tmp_path / "s.csv"
    write_racechrono_csv(session_factory([(20.0, 1.5)]), path, steering=False,
                         drop=("bearing", "x_rate_of_rotation", "y_rate_of_rotation", "z_rate_of_rotation"))
    assert main([str(path), "--no-trim"]) == 1
    assert "GPS heading and gyro" in capsys.readouterr().err


def test_a_missing_file_or_folder_is_a_clear_error_not_a_traceback(tmp_path, capsys):
    assert main([str(tmp_path / "typo.rcz")]) == 1
    err = capsys.readouterr().err
    assert "couldn't open" in err and "typo.rcz" in err and "Traceback" not in err
    assert main([str(tmp_path)]) == 1
    assert "couldn't open" in capsys.readouterr().err
