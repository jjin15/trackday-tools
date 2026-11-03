"""Detection parameters, and the named presets that stand in for them."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class DetectParams:
    """Thresholds for the steering-based slide detector (SI units)."""
    min_speed: float = 10.0      # m/s; ignore slow driving and the pits
    min_steer: float = 20.0      # deg of steering input
    min_yaw: float = 10.0        # deg/s of rotation the opposite way
    min_duration: float = 0.75   # s the mismatch must hold; shorter = counter-steer
    merge_gap: float = 0.5       # s; runs closer together than this are one slide
    smooth: float = 0.2          # s of smoothing on steering and yaw


@dataclass(frozen=True)
class SlipParams:
    """Thresholds for the no-steering detector, which looks at how sideways the car is."""
    min_slip: float = 12.0       # deg between where the car points and where it is going
    min_duration: float = 0.75   # s the slip must hold
    min_speed: float = 10.0      # m/s
    merge_gap: float = 0.5       # s
    smooth: float = 0.2          # s of smoothing on the slip angle


@dataclass(frozen=True)
class Preset:
    label: str
    summary: str
    params: DetectParams
    slip: SlipParams


# Values chosen by sweeping the thresholds on a real 19-lap session: duration is the
# biggest lever, then steering and counter-rotation. That session gave 21 / 31 / 40 slides
# from steering, and 14 / 28 / 39 from slip angle. The two detectors overlap but aren't the
# same: at strict, 10 of the 14 slip slides coincide with one of the 21 steering slides.
PRESETS: Dict[str, Preset] = {
    "strict": Preset("Strict", "Only obvious, sustained slides. Fewest false positives.",
                     DetectParams(), SlipParams()),
    "balanced": Preset("Balanced", "Also catches shorter, smaller slides.",
                       DetectParams(min_duration=0.5, min_steer=15.0, min_yaw=8.0),
                       SlipParams(min_slip=11.0, min_duration=0.5)),
    "loose": Preset("Loose", "Everything that could be a slide. Expect some false positives.",
                    DetectParams(min_duration=0.3, min_steer=10.0, min_yaw=5.0),
                    SlipParams(min_slip=10.0, min_duration=0.4)),
}
DEFAULT_PRESET = "strict"

MPH_PER_MS = 2.23694


@dataclass(frozen=True)
class ParamInfo:
    """How one threshold is described to a person (the web UI's Advanced panel)."""
    key: str
    label: str
    unit: str          # unit shown to the user: "s", "deg", "deg/s" or "speed"
    minimum: float
    maximum: float
    step: float
    methods: Tuple[str, ...] = ("steering", "slip")   # which detectors use this threshold


# merge_gap and smooth are deliberately not listed: they're internals, not tuning knobs.
PARAM_INFO: List[ParamInfo] = [
    ParamInfo("min_duration", "Must last at least", "s", 0.1, 3.0, 0.05),
    ParamInfo("min_steer", "Steering input of at least", "deg", 5, 90, 1, ("steering",)),
    ParamInfo("min_yaw", "Car turning the other way by at least", "deg/s", 2, 40, 1, ("steering",)),
    ParamInfo("min_slip", "Car pointing away from its direction of travel by at least", "deg",
              3, 45, 0.5, ("slip",)),
    ParamInfo("min_speed", "Only when going faster than", "speed", 3, 30, 0.5),
]
