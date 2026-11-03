# racelog

Reads RaceChrono sessions and track files. The shared library behind [SlideFinder](../slidefinder/README.md) and [Lap Compare](../lapcompare/README.md).

```python
from racelog import loader

parts = loader.list_parts("session.rcz")            # an .rcz can hold several drives
session = loader.load_session("session.rcz", part=loader.default_part("session.rcz"))
session.df            # 50 Hz frame: t, lap_number, latitude, longitude, speed, steer, yaw, ...
session.fingerprint   # a short id for this recording, the same from the CSV or the .rcz
```

- **`loader`**: opens either an `.rcz` archive or a CSV export (by looking at the file, not its name).
- **`rcz`**: reads `.rcz` archives directly, including the raw per-channel files.
- **`racechrono`**: reads CSV exports (format 3).
- **`tracks`**: RaceChrono track files, the start/finish and checkpoint gates, gate crossings and sectors.
- **`start`**: finds when the car actually leaves the pits and starts driving.
- **`testing`**: synthetic sessions and writers for tests in any package.

The `.rcz` layout is not documented by RaceChrono. What is known, and how it was worked out, is in [`docs/racechrono-formats.md`](../../docs/racechrono-formats.md).

```
.venv/bin/pip install -e "packages/racelog[dev]"
.venv/bin/python -m pytest packages/racelog
```
