"""Command line: `lapcompare` starts the web app."""
from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="lapcompare",
        description="Compare laps from RaceChrono sessions. Starts the Lap Compare web app on this "
                    "computer; drop a session (.rcz or CSV) onto the page.")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--no-open", action="store_true", help="don't open a browser tab")
    args = ap.parse_args(argv)
    from .server import serve

    serve(args.port, open_browser=not args.no_open)
    return 0


if __name__ == "__main__":
    sys.exit(main())
