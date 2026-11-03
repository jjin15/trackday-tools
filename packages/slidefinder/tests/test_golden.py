"""Regression: the real session must keep producing exactly the same slides.

Skipped when the private session file isn't around. Set SLIDEFINDER_GOLDEN_CSV to point
at it, or leave a session_*.csv in the repository root.
"""
import glob
import os
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[3]          # the repository root
GOLDEN = Path(__file__).parent / "local" / "golden_slides.csv"


def _session_csv():
    env = os.environ.get("SLIDEFINDER_GOLDEN_CSV")
    if env:
        return env
    hits = sorted(glob.glob(str(ROOT / "session_*.csv")))
    return hits[0] if hits else None


@pytest.mark.skipif(_session_csv() is None or not GOLDEN.exists(),
                    reason="private session file or golden output not available")
def test_real_session_matches_golden(tmp_path):
    from slidefinder.cli import main

    out = tmp_path / "slides.csv"
    assert main([_session_csv(), "--out", str(out)]) == 0
    golden = pd.read_csv(GOLDEN)
    result = pd.read_csv(out)
    # the export has gained columns since the golden file was made; the original ones must not change
    pd.testing.assert_frame_equal(result[list(golden.columns)], golden)
    assert {"session_id", "session_start", "source_lap"} <= set(result.columns)
    assert result["source_lap"].between(8, 26).all()            # RaceChrono's own lap numbers


@pytest.mark.skipif(_session_csv() is None, reason="private session file not available")
def test_slip_detector_agrees_with_steering_detector_on_real_session():
    """The fallback should mostly flag the same slides the steering detector does."""
    from slidefinder.detect import slip, steering
    from slidefinder.presets import PRESETS
    from racelog.racechrono import load_session

    session = load_session(_session_csv())
    steer_runs = steering.find_runs(session, PRESETS["strict"].params)
    slip_runs = slip.find_runs(session, PRESETS["strict"].slip)

    def overlaps(a, others):
        return any(a.start < o.end and o.start < a.end for o in others)

    matched = sum(overlaps(r, steer_runs) for r in slip_runs)
    assert len(slip_runs) >= 8
    assert matched / len(slip_runs) >= 0.6      # measured 10/14 when this was written


def _session_rcz():
    env = os.environ.get("SLIDEFINDER_GOLDEN_RCZ")
    if env:
        return env
    hits = sorted(glob.glob(str(ROOT / "session_*.rcz")))
    return hits[0] if hits else None


@pytest.mark.skipif(_session_csv() is None or _session_rcz() is None,
                    reason="needs the private session as both a CSV and an .rcz")
def test_rcz_gives_the_same_slides_as_the_csv_export(tmp_path):
    """Reading the .rcz directly must find the same slides, in the same sectors and clips."""
    from slidefinder.cli import main

    out_csv, out_rcz = tmp_path / "csv.csv", tmp_path / "rcz.csv"
    assert main([_session_csv(), "--out", str(out_csv)]) == 0
    assert main([_session_rcz(), "--out", str(out_rcz)]) == 0
    a, b = pd.read_csv(out_rcz), pd.read_csv(out_csv)
    assert len(a) == len(b) == 21

    used = set()
    for _, row in a.iterrows():
        match = [j for j, other in b.iterrows()
                 if j not in used and other["lap"] == row["lap"]
                 and abs(other["session_time_s"] - row["session_time_s"]) < 0.5]
        assert match, f"no CSV slide matches lap {row['lap']} at {row['session_time']}"
        used.add(match[0])
        other = b.loc[match[0]]
        assert other["sector"] == row["sector"] and other["clip"] == row["clip"]
        assert abs(other["severity"] - row["severity"]) <= 0.03 * other["severity"] + 3.0
