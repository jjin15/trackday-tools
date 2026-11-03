"""Map data time onto the GoPro clips."""
from __future__ import annotations

from typing import List, Tuple, Union

from racelog.util import fmt_time


def parse_duration(text: str) -> float:
    """'12:48' -> 768.0, '768' -> 768.0"""
    mins, _, secs = text.strip().rpartition(":")
    return (float(mins) * 60 if mins else 0.0) + float(secs)


def parse_clip_lengths(text: str) -> List[float]:
    """'12:48,12:48,05:10' -> [768.0, 768.0, 310.0]"""
    return [parse_duration(x) for x in text.split(",")]


def locate_clip(video_t: float, clip_lengths: List[float]) -> Tuple[Union[int, str], str]:
    """Return (clip number from 1, mm:ss into that clip) for a time on the combined video.

    The last length in clip_lengths repeats for any clips beyond the list.
    """
    if video_t < 0:
        return "", ""
    start, n = 0.0, 0
    while True:
        length = clip_lengths[min(n, len(clip_lengths) - 1)]
        if video_t < start + length:
            return n + 1, fmt_time(video_t - start)
        start += length
        n += 1


def solve_offset(session_time: float, clip_lengths: List[float], clip: int, clip_time: float) -> float:
    """The offset that puts a known slide where it really is in the video.

    `session_time` is the slide's time in the data (seconds from the on-track start). It was
    seen `clip_time` seconds into clip number `clip` (from 1). Returns seconds to add to data
    time to get video time, the same value as --offset.
    """
    if clip < 1:
        raise ValueError("Clip numbers start at 1.")
    before = sum(clip_lengths[min(i, len(clip_lengths) - 1)] for i in range(clip - 1))
    return before + clip_time - session_time
