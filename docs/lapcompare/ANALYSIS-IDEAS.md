# Lap Compare: post-track-day analysis ideas

**Read this when:** building any "where am I losing time?" analysis. These are the user's ideas, written down with the reasoning, a feasibility check on a real session, and the open questions. **Nothing here is built.** Prerequisites (track-position alignment, gate-based lap timing) are in `DESIGN.md`.

## The user's goals
1. Find the corners/sectors that are **most inconsistent**.
2. Find where the **most time is left on the table**.
3. Point out the **largest areas of improvement**.
Methods the user proposed: ignore cool-down and traffic laps (a lap more than ~1.5 s slower than the best), **but still take a sector from such a lap if it is the fastest sector** (a traffic lap can have great early sectors and be ruined later); and use **overall G in each corner as a measure of grip utilization**.

## Feasibility check on the real session (laps 8-26 of the sample `.rcz`)
Computed from start/finish and checkpoint gate crossings (Sonoma has 8 gates, so 8 sectors), 18 complete laps. This was a throwaway script, not product code; the numbers are for orientation.
- Lap times 109.71 s (best) to 127.08 s. **Only 7 of 18 laps are within 1.5 s of the best**; the rest range 112.5-127.1 s. So a fixed 1.5 s rule leaves a small sample (consider a looser threshold, or 1.5% of the best lap time, or using it only for "best lap" tagging and a percentile for consistency stats).
- **The user's traffic-lap idea is borne out:** 4 of the 8 sectors have their fastest time on a lap that is *not* within 1.5 s (lap 6 of the part, 114.5 s, holds the fastest T11->T1-2, T1-2->T3 and T3->T4-5; another lap holds the fastest T8-9->T10). A rule that discarded slow laps outright would lose those.
- Sum of best sectors (all laps) = **108.52 s**, matching RaceChrono's own `optimalLaptime` (108.516 s). So the gate-based sector times are trustworthy, and the "ideal lap" is 1.2 s faster than the best actual lap.
- Per sector over the clean laps (seconds): median minus best ranges 0.10-0.33; standard deviation 0.08-0.37. Largest median-minus-best: T11->T1-2 (0.33), T4-5->T6 (0.23), T3->T4-5 (0.22), T10->T11 (0.19), T8-9->T10 (0.18). Largest spread: T6->T7 (std 0.37), T10->T11, T7->T8-9, T4-5->T6 (about 0.2). Sum of (median - best) over sectors = 1.54 s.
- Note the two rankings disagree: the sector costing the most on average (T11->T1-2) is not the most variable (T6->T7). Both views are useful and should both be shown.
- Context from SlideFinder on the same session: T6->T7 is also where most slides happen (8 of 21), including the two biggest. High variability there and slides there may be the same story.

## Ideas, with how to build them
### 1. Lap classes
- **Complete lap**: bounded by two start/finish crossings (excludes out/in laps).
- **Best lap**: fastest complete lap. **Clean lap**: complete and within a threshold of best (default 1.5 s as the user said; make it configurable; see the sample-size warning above).
- Everything else (cool-down, traffic, mistakes) is excluded from *consistency statistics* but not from the *pool of best sectors*.
### 2. Best sectors from any lap, with a caveat
The "ideal lap" = sum over sectors of the fastest time from **all** laps. Caveat to record in the UI: a sector's time depends on the speed carried in, so a fastest sector that followed a fast previous sector may not be combinable with a fast sector elsewhere. Show **entry speed** next to each best sector, and flag best sectors whose entry speed is unusually high. Corner-exit-to-corner-exit sectors (cut at the apex or exit rather than at a checkpoint) reduce this.
### 3. Inconsistency ranking
Per sector and per corner, over clean laps: standard deviation, IQR, and `median - best`. Rank by each; show both because they answer different questions (reliable but slow vs fast but erratic).
### 4. Time left on the table
- Within a session: `median clean time - best time` per sector; the sum is the potential gain from consistency alone (1.54 s on the sample); share per sector shows where it comes from.
- Across sessions: current session's median vs the best across the library for that sector (needs `DESIGN.md`'s library and tags, so that a different tire or a hot day is not read as lost time).
- Also useful: `best sector - theoretical` from a reference lap the user picks (a friend's lap, a target).
### 5. Corners, not only checkpoints
Gate-defined sectors (8 at Sonoma) are coarse, and tracks without checkpoints have none. Detect corners from the reference line (curvature peaks) and the speed trace (apex = local speed minimum), then split each into **brake zone, turn-in to apex, apex to exit**. Per-corner metrics: brake point (distance and pressure), minimum speed, throttle-on point, exit speed, time from entry to exit. This is where "what exactly went wrong" lives (late throttle vs low apex speed vs early brake).
### 6. Grip utilization from overall G
- Combined G = `sqrt(lat^2 + long^2)`. Estimate the car's usable limit from the data (for example the 95th to 99th percentile of combined G over clean laps) and report each corner's peak and mean combined G as a fraction of it. Low utilization at a slow apex = speed being left unused; utilization near 1 with a slow time = car-limited, not driver-limited.
- A **traction circle** per corner (long vs lat G), laps overlaid, makes this visible.
- **Data caveats:** the CSV has a calculated `combined_acc` but an `.rcz` does not. Compute it from CAN lateral/longitudinal G (stored in m/s^2 in the `.rcz`) or from the IMU, gravity-projected (logger tilt was ~6 degrees on the sample) with the stationary bias removed. Elevation change and banking add vertical acceleration and bias G in some corners (Sonoma has big elevation change); consider a per-track note or correction. CAN acceleration may be filtered differently from the IMU; check which looks right before choosing one.
### 7. Largest areas of improvement
A ranked list combining potential time gain with how repeatable the loss is, each with a plain-language reason built from the metrics (for example: "T6->T7: 0.15 s average loss, mostly from lap-to-lap variation in apex speed, std 0.37 s"). Rank by `potential_gain x reliability` rather than raw gain, so a one-off outlier does not top the list.
### 8. Traffic beyond lap time
A slow lap does not say *where* traffic was. Flag individual sectors as disturbed when they are slow relative to that sector's distribution while neighbouring sectors on the same lap are normal; also unusual lifts or brake taps on a straight where the driver never lifts on other laps. Disturbed sectors drop out of consistency statistics but can still be "best".
### 9. Cross-session views
Same analysis, grouped by session or tag: did the new tires gain time in sector X; is Sunday more consistent than Saturday; session-to-session progress per sector.

## Open questions
- Threshold for "clean": fixed 1.5 s, a percentage, or a percentile? (Only 7/18 laps pass 1.5 s on the sample.)
- Sector boundaries: use track checkpoints, detected corners, or both? How to handle tracks with none?
- How to estimate the grip limit fairly when the driver never reaches it (the 99th percentile then understates it).
- Treating a mid-lap pit or spin lap: exclude the whole lap from statistics, or only the affected sectors?
- Weighting: should recent laps count more? Should the first laps on cold tires be down-weighted?
- How to present uncertainty: with 7 clean laps a standard deviation is a rough guide; say so in the UI.
- Whether to let SlideFinder's slides feed in (a slide in a sector explains a slow time there).

## First steps when resuming
1. Promote gate-crossing lap timing and per-sector times into `racelog` (`racelog.timing`) with tests, using the oracle above (108.52 s optimal, 109.714 s best).
2. Add lap classification and the sector table (best, median, std, median-best) to `lapcompare` for a single session; show it in the UI. This needs no library or alignment work and delivers ideas 1-4 and 7 for one session.
3. Then `DESIGN.md`: reference line and track-position alignment, then the library, then cross-session views (idea 9).
4. Corners and grip utilization (5, 6) after that; they need the aligned grid and a combined-G computation in `racelog`.

## Appendix: the feasibility script (throwaway)
Reproduces the sector numbers above. Run with the repo venv; point `R` at a session `.rcz` (its embedded track supplies the gates).
```python
# sector k starts at gate order[k] and ends at the next gate (the last one ends at start/finish)
import numpy as np
from racelog import loader, tracks

R = "session.rcz"
s = loader.load_session(R)                                   # default part
gates = tracks.load_gates(loader.embedded_track(R).path)
crossings, order = tracks.find_crossings(s, gates)           # order[0] is start/finish
by_gate = {g: [t for t, n in crossings if n == g] for g in order}
sf = by_gate[order[0]]
rows = []
for a, b in zip(sf, sf[1:]):                                 # complete laps only
    marks = [next((t for t in by_gate[g] if a <= t < b), None) for g in order[1:]]
    if None not in marks:
        rows.append(np.diff([a] + marks + [b]))              # one time per sector
L = np.array(rows); lap = L.sum(axis=1)
clean = lap <= lap.min() + 1.5
for k in range(L.shape[1]):
    col = L[:, k]
    print(order[k], "best", col.min(), "median(clean)", np.median(col[clean]), "std(clean)", col[clean].std(ddof=1))
print("sum of best sectors", L.min(axis=0).sum(), "vs best lap", lap.min())
```
