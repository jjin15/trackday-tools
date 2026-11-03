"""Choose a detector for a session and run it."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Optional

from ..presets import PRESETS
from racelog.session import Session
from . import Run, slip, steering


@dataclass
class Detection:
    runs: List[Run]
    method: str        # "steering" or "slip"
    note: str          # one line a person can read about how slides were found


STEERING_NOTE = "Slides = steering one way while the car rotates the other (opposite lock)."
SLIP_NOTE = ("No steering angle in this log, so slides = the car pointing well away from "
             "where it is travelling (slip angle). This finds a different, usually smaller, "
             "set than opposite lock.")


class DetectionUnavailable(Exception):
    """The session doesn't have the channels the requested detector needs."""


def detect(session: Session, preset: str = "strict", method: str = "auto",
           **overrides) -> Detection:
    """Run slide detection. `overrides` replace individual thresholds of the preset."""
    chosen = PRESETS[preset]
    if method == "auto":
        method = "steering" if session.has_steering else "slip"
    if method == "steering":
        if not session.has_steering:
            raise DetectionUnavailable("This log has no steering angle channel.")
        fields = chosen.params.__dataclass_fields__
        params = replace(chosen.params, **{k: v for k, v in overrides.items() if k in fields and v is not None})
        return Detection(steering.find_runs(session, params), "steering", STEERING_NOTE)
    if method == "slip":
        if not session.has_slip_inputs:
            raise DetectionUnavailable(
                "This log needs GPS heading and gyro (yaw rate) data to estimate slip.")
        fields = chosen.slip.__dataclass_fields__
        params = replace(chosen.slip, **{k: v for k, v in overrides.items() if k in fields and v is not None})
        return Detection(slip.find_runs(session, params), "slip", SLIP_NOTE)
    raise ValueError(f"Unknown method '{method}'")
