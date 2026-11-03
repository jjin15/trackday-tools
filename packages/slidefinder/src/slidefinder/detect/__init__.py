"""Slide detectors. Each returns a list of `Run`s for the report step to describe."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class Run:
    """One detected slide, as sample indices into the session frame."""
    start: int                 # first sample (inclusive)
    end: int                   # last sample (exclusive)
    duration: float            # seconds
    severity: float
    details: Dict[str, float] = field(default_factory=dict)   # detector-specific columns
