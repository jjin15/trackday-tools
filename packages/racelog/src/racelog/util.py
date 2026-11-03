"""Small shared helpers."""
from __future__ import annotations


def fmt_time(sec: float) -> str:
    """Format seconds as mm:ss.ss, with a leading '-' for negative times."""
    sign = "-" if sec < 0 else ""
    sec = abs(sec)
    return f"{sign}{int(sec // 60):02d}:{sec % 60:05.2f}"
