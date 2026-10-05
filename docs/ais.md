# AIS reception and regional observations

`ais_collector.py` runs `/root/AIS-catcher` on V4MAIN01, JSON output (`-o 5`), automatic tuner gain, RTL AGC enabled and 192K bandwidth. It receives both AIS channels around 162 MHz. `ais_store.py` persists targets and met/hydro observations in `data/watchkeeper.db`, distinguishing position/motion ages and calculating distance/bearing from configured observer coordinates.

`jobs-v4.jsonc` retains 120 s AIS dwell; `job_manager.py` currently caps background slots to **30 s** with Tower recording configured. Airband is revisited frequently and METEOR overrides AIS. This is intermittent monitoring rather than continuous all-message reception.

The dashboard map distinguishes local/regional targets, base stations and age. `/api/state` contains AIS/met-hydro data; no dedicated `/api/ais` route exists in the installed dashboard. Stored records support Aurora Botnia and local base stations. [AIS Hydro study](ais-hydro-cadence.md) finds sub-ten-minute observation steps for Vaasa/Pietarsaari water levels, unlike examined weather sites. Packet receipt, observation time and value changes are distinct measurements.

Indoor antenna placement and shared dwell limit reception. Zero messages alone is not an RF failure: native sample-processing evidence feeds health independently of decoded traffic. Collector deadlines, nonblocking output and process-group cleanup prevent unbounded ownership. Retained gain trials do not establish optimal gain or sensitivity. See [watchdog](watchdog-and-recovery.md) and [troubleshooting](troubleshooting.md).
