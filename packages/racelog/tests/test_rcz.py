import json
import zipfile

import numpy as np
import pytest

from racelog import loader, rcz
from racelog.testing import GATE_SF, write_racechrono_rcz, write_two_part_rcz


def test_is_rcz_looks_at_content_not_the_name(tmp_path, session_factory):
    rcz_path, csv_path = tmp_path / "data.bin", tmp_path / "x.rcz"
    write_two_part_rcz(rcz_path)
    csv_path.write_text("timestamp,lat\n")
    assert rcz.is_rcz(rcz_path) and not rcz.is_rcz(csv_path) and not rcz.is_rcz(tmp_path / "nope")


def test_parts_are_listed_and_the_busiest_is_the_default(tmp_path, session_factory):
    path = tmp_path / "s.rcz"
    write_two_part_rcz(path)
    parts = rcz.list_parts(path)
    assert [len(p.laps) for p in parts] == [1, 2]
    assert parts[1].label.startswith("Part 2: laps 2–3")
    assert rcz.default_part(parts) == 1
    info = loader.list_parts(path)
    assert [p.first_lap for p in info] == [1, 2] and [p.last_lap for p in info] == [1, 3]


def test_loaded_session_matches_what_was_written(tmp_path, session_factory):
    path = tmp_path / "s.rcz"
    _, second = write_two_part_rcz(path)
    s = rcz.load_session(path)                                  # default = part 2
    assert s.t0 == pytest.approx(second.t0, abs=0.01)
    assert s.meta["track name"] == "Synthetic Track" and s.has_steering
    assert s.df["speed"].median() == pytest.approx(30.0, abs=0.01)
    # steering was stored at 5 Hz; reading it back should follow the original closely
    t = second.df["t"].to_numpy()
    original = np.interp(s.df["t"].to_numpy(), t, second.df["steer"].to_numpy())
    assert np.nanmedian(np.abs(s.df["steer"].to_numpy() - original)) < 2.0
    assert s.df["steer"].isna().mean() < 0.01                  # only the last fraction of a second is unsampled
    # laps: lap 2 for the first half, lap 3 for the second
    laps = s.df["lap_number"]
    assert laps[s.df["t"] < 29].eq(2).all() and laps[s.df["t"] > 31].eq(3).all()
    first = rcz.load_session(path, part=0)
    assert first.t0 == pytest.approx(second.t0 - 6 * 3600, abs=0.01)
    assert first.df["lap_number"].dropna().eq(1).all()


def test_embedded_track_is_found_only_when_usable(tmp_path, session_factory):
    session = session_factory([])
    with_track, bare = tmp_path / "with.rcz", tmp_path / "bare.rcz"
    write_racechrono_rcz(with_track, [session], [[(1, 0.0, None)]], track_name="Nowhere Raceway",
                         embedded_track=[GATE_SF])
    write_racechrono_rcz(bare, [session], [[(1, 0.0, None)]], track_name="Nowhere Raceway")
    assert loader.embedded_track(with_track).name == "Nowhere Raceway"
    assert loader.embedded_track(bare) is None
    assert loader.track_name(bare) == "Nowhere Raceway"


def test_bad_archives_raise_readable_errors(tmp_path):
    track_only = tmp_path / "track.rcz"
    with zipfile.ZipFile(track_only, "w") as z:
        z.writestr("trackId.json", json.dumps({"track": {"name": "X", "traps": [GATE_SF]}}))
    with pytest.raises(rcz.RczFormatError, match="track file, not a session"):
        rcz.list_parts(track_only)

    no_gps = tmp_path / "nogps.rcz"
    with zipfile.ZipFile(no_gps, "w") as z:
        z.writestr("session.json", json.dumps({"laps": []}))
        z.writestr("sessionfragment.json", json.dumps({"firstTimestamp": 1, "latestTimestamp": 2, "devices2": []}))
    with pytest.raises(rcz.RczFormatError, match="no GPS data"):
        rcz.load_session(no_gps)

    broken = tmp_path / "broken.rcz"
    broken.write_bytes(b"PK\x03\x04 not really a zip")
    with pytest.raises(rcz.RczFormatError, match="valid .rcz"):
        rcz.list_parts(broken)


def test_can_acceleration_is_stored_in_ms2_and_listed_as_g(tmp_path, session_factory):
    path = tmp_path / "s.rcz"
    write_racechrono_rcz(path, [session_factory([])], [[(1, 0.0, None)]], can_lateral_ms2=9.80665)
    ch = rcz.Channels(path, rcz.list_parts(path)[0])
    _, values = ch.can[7]
    assert np.allclose(values, 9.80665)                              # stored as m/s^2
    meta = rcz.CAN_CHANNELS[7]
    assert meta.key == "lateral acc (canbus)" and np.allclose(values * meta.factor, 1.0)   # shown as 1 G
