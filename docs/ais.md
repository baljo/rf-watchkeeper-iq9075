# AIS reception and regional observations

`ais_collector.py` runs `/root/AIS-catcher` on V4MAIN01, JSON output (`-o 5`), automatic tuner gain, RTL AGC enabled and 192K bandwidth. It receives both AIS channels around 162 MHz. `ais_store.py` persists targets and met/hydro observations in `data/watchkeeper.db`, distinguishing position/motion ages and calculating distance/bearing from configured observer coordinates.

`jobs-v4.jsonc` retains 120 s AIS dwell; `job_manager.py` currently caps background slots to **30 s** with Tower recording configured. Airband is revisited frequently and METEOR overrides AIS. This is intermittent monitoring rather than continuous all-message reception.

The dashboard map distinguishes local/regional targets, base stations and age. `/api/state` contains AIS/met-hydro data; no dedicated `/api/ais` route exists in the installed dashboard. Stored records support Aurora Botnia and local base stations. [AIS Hydro study](ais-hydro-cadence.md) finds sub-ten-minute observation steps for Vaasa/Pietarsaari water levels, unlike examined weather sites. Packet receipt, observation time and value changes are distinct measurements.

Indoor antenna placement and shared dwell limit reception. Zero messages alone is not an RF failure: native sample-processing evidence feeds health independently of decoded traffic. Collector deadlines, nonblocking output and process-group cleanup prevent unbounded ownership. Retained gain trials do not establish optimal gain or sensitivity. See [watchdog](watchdog-and-recovery.md) and [troubleshooting](troubleshooting.md).

## AIS map reception history — verified 8 October 2026

Both the regional and local AIS maps use the shared Recent / 24 hours / 7 days selector (default 24 hours). Changing it redraws both maps. Recent uses existing live target timeouts (moving targets 30 minutes, stationary/unknown-speed positions 1 hour, base stations 24 hours; identity-only targets 2 hours). Live API inventory can include identities without plottable positions.

`/api/state` adds `ais_history_targets`: `historical_targets(168, 500)` reads the latest retained position per MMSI from ais_targets, orders by position_seen descending, includes positions within seven days, validates coordinates and a 250 km observer radius, and caps at 500. The browser filters position_seen against server_time for 24/168 hours, rejecting future timestamps. Static identity messages update last_seen without refreshing position_seen. This is last-known reception history, not a track of every past position or current vessel locations. Local range filters may reduce displayed counts.

Hover text gives Position received with browser-local timestamp and elapsed reception age. Historical targets outside the live positioned MMSI set are faded to opacity 0.65 and receive name/MMSI plus age labels; other targets older than 30 minutes fade to 0.30. Local map labels are spaced with connector lines where displaced. Reception age describes the last position message, not current vessel freshness.

See [dated validation, tests, restart, rollback and showcase evidence](ais-dashboard-completion-20261008.md). Counts in that report are time-dependent observations, never fixed expected totals.
