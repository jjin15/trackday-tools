# Lap Compare

Overlay laps from a RaceChrono session and compare any logged signal against distance. Runs on your own computer; your data never leaves it.

```
.venv/bin/pip install packages/racelog packages/lapcompare
.venv/bin/lapcompare
```

A page opens (port 8766). Drop a session file (`.rcz`, or a CSV export) onto it.

- Pick up to 8 laps. The three fastest start selected.
- Tick any signals in the left list; each gets its own chart on a shared distance axis. Speeds are in mph.
- **Delta time** shows time gained or lost against a reference lap you choose.
- The four wheel speeds are offered as one combined plot.
- **Table view** gives min / average / max per lap for the chosen signals.
- **Load slides** reads the CSV exported from [SlideFinder](../slidefinder/README.md) and marks each slide on its lap. It matches by session, so slides from another session are ignored and reported.
- A session `.rcz` with several drives has a *Part* menu.

This is the first version: one session at a time, distance measured from the start of each lap. Comparing laps across different sessions, and the post-track-day analysis (inconsistent corners, time left on the table, grip use), are designed but not built. See [`docs/lapcompare/`](../../docs/lapcompare/).

`.rcz` files do not contain RaceChrono's *calculated* channels (calculated speed, lean angle and so on); only CSV exports do.

```
.venv/bin/pip install -e packages/racelog -e "packages/lapcompare[dev]"
.venv/bin/python -m pytest packages/lapcompare
```
