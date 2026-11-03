# RaceChrono file formats (reverse-engineered)

**Read this when:** touching `racelog/rcz.py`, `racelog/racechrono.py`, or anything that depends on what a channel's units or sample rate are.

**Status:** worked out by comparing ONE `.rcz` archive (RaceChrono v10.2.4, a car with CAN-bus data, 2 parts, 26 laps) with ONE CSV export of the same session. RaceChrono does not document either format. Treat anything marked *inferred* as unverified. Other cars, loggers or app versions may differ.

## The relationship in one paragraph
The CSV export is RaceChrono's own resampling of the `.rcz`: every channel linearly interpolated (gear is held, not interpolated) onto a union of all channels' sample times. Linear interpolation of the raw channels reproduces the CSV: GPS speed, distance, latitude, accelerometer, gyro and CAN speed match to within rounding. So reading the `.rcz` loses nothing, and it is ~12x smaller (20 MB vs 250 MB for the same session).

## `.rcz` archive (a zip)
```
session.json                       session-wide: track name, all laps, best/optimal lap times
trackId.json                       the track (same format as a standalone track .rcz)
sessionfragment.json               part 0 (the first drive): time range, device list
channel_*  channel2_*              part 0 channel files
resume_1/sessionfragment.json      part 1 (first resume) ... resume_N for later ones
resume_1/channel_*  channel2_*
```
A **part** is one stretch of continuous logging. Stopping and resuming in the app starts a new part. In the sample file, part 0 = laps 1-7 (morning), `resume_1` = laps 8-26 (afternoon), six hours apart. Lap numbers continue across parts. The user's CSV export covered only `resume_1`.

### `session.json`
`trackName`, `bestLaptime` (ms), `optimalLaptime` (ms, sum of best sectors), `lapCount` (completed laps), `firstTimestamp`/`latestTimestamp` (unix ms), and `laps`: `[{number, sessionResume, startTimestamp, finishTimestamp?, isInvalid}]`. `sessionResume` is the part index. A lap with no `finishTimestamp` was still running when logging stopped (laps 7 and 26 in the sample).
**Useful oracle:** `optimalLaptime` 108516 ms equals the sum of the best sector times computed from the track gates (108.52 s), and `bestLaptime` 109714 ms equals the fastest lap.

### `sessionfragment.json`
`firstTimestamp`/`latestTimestamp` (unix ms), `lengthDistance` (mm), `devices2`: `[{selector: {id, model, type}}]`. Device types: **1 GPS** (id 100), **2 accelerometer** (101), **3 gyro** (102), **12 CAN bus** (200). Ids are from the sample file; `rcz.py` looks them up by type.

### `trackId.json`
`{"track": {name, traps: [...]}}`. Each trap (gate): `name`, `centerLatitude`/`centerLongitude` (1/6,000,000 deg, i.e. 1/100000 arc-minute), `bearing` (1/1000 deg, the direction of travel across the line), `width` (mm, full width), `type` (**3 = start/finish, 4 = checkpoint**), `uniDirectional`. A session `.rcz` carries its track, so sectors work with no separate file; `racelog.tracks.read_track_json` accepts either.

### Channel files
Names: `channel_<type>_<id>_0_<channel>_<kind>` for GPS/accelerometer/gyro. Little-endian.

| Device | Channel | File suffix | Type | Meaning / scale | Status |
|---|---|---|---|---|---|
| GPS (25 Hz) | 1 | `_1_1` | int64 | sample time, unix ms | verified |
| | 2 | `_2_1` | int64 | distance travelled, mm (cumulative) | verified exact vs CSV |
| | 3 | `_3_1` | int32 pairs | latitude, longitude in 1/6,000,000 deg | verified exact |
| | 4 | `_4_0` | int32 | speed, /1000 = m/s | verified exact |
| | 5 | `_5_0` | int32 | altitude, /1000 = m | verified |
| | 6 | `_6_0` | int32 | bearing, /1000 = deg | verified (interpolate as vectors) |
| | 30007 / 30002 / 30003 / 46 | `_0` | int32 | accuracy /1000 m, satellites, fix type, battery /1000 % | inferred from first-row match |
| Accelerometer (25 Hz) | 1 | `_1_1` | int64 | time, unix ms | verified |
| | 9, 10, 11 | `_0` | int32 | x, y, z in **mm/s^2**; /9806.65 = G | verified exact |
| Gyro (25 Hz) | 1 | `_1_1` | int64 | time, unix ms | verified |
| | 12, 13, 14 | `_0` | int32 | x, y, z in 1/1000 deg/s | verified exact |

The IMU axes are the *logger's*, not the car's. The logger in the sample was tilted ~6 degrees from vertical, so gyro z is close to, not exactly, yaw. `racelog`-side code that needs true yaw should project the gyro onto the gravity direction (see `slidefinder/detect/slip.py: imu_yaw_rate`).

### CAN bus channels (device 12)
Per channel number `P`: `channel_12_200_P_1_1` = sample times (int64 ms); `channel2_12_200_P_P_3` = values (**float64, already in display units**); `channel_12_200_P_2_1` = all zeros (meaning unknown). Channel `1` has times only (588k samples, purpose unknown, ignored). Rates are irregular: most channels tens of Hz, **steering ~5 Hz** (median gap 208 ms, 90th percentile 426 ms).

The channel numbers are RaceChrono's built-in ones, matched to CSV column names by comparing values over time (`rcz.CAN_CHANNELS`):
`4` speed (canbus) | `7` lateral acc | `8` longitudinal acc | `38` pitch | `1001` steering angle | `1002` brake pos | `1004` gear | `1029` engine torque | `5017` torque | `10024` rpm | `10025` throttle pos | `10026` coolant temp | `10031` air temp | `10066` engine oil temp | `10071` accelerator pos | `33801` brake pressure rear | `66569` brake pressure front | `99320` wheel speed rr | `132088` rl | `164856` fr | `197624` fl.
Numbers above 32768 are `index * 32768 + base id` (brake pressure = base 1033, wheel speed = base 1016). Order within a group is not the obvious one (rear before front; rr, rl, fr, fl), so it was matched on data, not assumed.
**Units that differ from the CSV:** lateral and longitudinal acceleration (7, 8) are stored in **m/s^2** while the CSV shows G. Everything else matched the CSV units.
Pairs that matched ambiguously and were resolved by exact-match fraction: `1029` vs `5017` (engine torque vs torque) and `10025` vs `10071` (throttle pos vs accelerator pos). If a future file looks swapped, check these first.

### What is NOT in an `.rcz`
RaceChrono's *calculated* channels (CSV source `calc`): calculated speed, lateral/longitudinal acceleration, combined acceleration, lean angle. They appear only in CSV exports. Anything needing combined G must compute it (see `docs/lapcompare/ANALYSIS-IDEAS.md`).

## CSV export (format 3)
- Lines 1-8: metadata (`Format,3`, `Session title`, `Track name`, ... `Created`, `Note`), a blank line, then **header row, units row, source row** (e.g. `100: gps`, `200: canbus`, `calc`, `101: acc`, `102: gyro`); data follows.
- **Duplicate column names.** `speed` appears three times (gps, calc, canbus), `lateral_acc` and `longitudinal_acc` twice, `device_update_rate` four times. Always pick by (name, source); `racechrono.Header.find(name, prefer_source)` does this. Never use the first match blindly.
- Rows are on a union of all channels' sample times (~280 rows/s on average, 670k rows for 40 min). Values are interpolated between samples.
- `lap_number` is blank outside laps; `distance_traveled` is cumulative metres; `timestamp` is unix seconds.
- When binned to 50 Hz by time, the CSV leaves a few isolated empty 20 ms bins (113,368 samples vs 119,207 from the `.rcz` for the same data). The CSV loader drops those bins, so its frame is not perfectly uniform; the `.rcz` loader's is. No measured effect on slide results.
- The CSV's first row is ~4 ms after the `.rcz`'s first GPS sample, so `Session.t0` differs by ~0.004 s between formats; `Session.fingerprint` rounds to the second for that reason (a recording that starts within a few ms of a half-second boundary could in principle get two ids).

## How `racelog` reads them
`loader.load_session(path, hz=50, part=None)` sniffs the file (zip magic), then:
- `.rcz`: `rcz.list_parts` -> `rcz.Channels` (raw arrays) -> `rcz.load_session` linearly interpolates onto bin centres `(i+0.5)/hz`; bearing is interpolated as a vector; lap numbers come from `session.json`; gear is held.
- CSV: `racechrono.load_session` reads by (name, source) and bins by mean.
Both return a `Session` (see `docs/ARCHITECTURE.md`). The default part is the one with the most laps.
