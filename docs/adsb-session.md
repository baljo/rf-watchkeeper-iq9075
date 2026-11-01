# Temporary unattended ADS-B session

Deployed 1 November 2026 on the live IQ-9075. The requested 12-hour lease is
`20261101T190045Z`: **2026-11-01 19:00:45.977 UTC through 2026-11-02
07:00:45.977 UTC** (21:00:45 through 09:00:45 Europe/Helsinki).
This is temporary reception, not a permanent RF scheduling change.

## Runtime and RF

The inspected host is aarch64 Qualcomm Linux Reference Distro 2.0, with systemd
and Docker, but no discovered host compiler, apt, dump1090 or readsb. Host
`/usr/local/bin/rtl_*` tools and `librtlsdr.so.2.0.3` were present; no host driver
was replaced. An existing Debian bookworm ARM64 container environment supplied
build dependencies. The isolated image `rf-watchkeeper-adsb:20261101` contains
FlightAware dump1090 and the RTL-SDR Blog vendor driver. Both upstream revisions
are pinned in [Dockerfile](../adsb-session/Dockerfile); the image ID, binary
hashes and source revisions are retained in per-session provenance. The original
build cloned those exact revisions before the Dockerfile was pinned; the
pinned Dockerfile was not independently rebuilt. Debian dependency versions are
not a complete reproducible package lock.

Live initialization positively identified **RTLSDRBlog Blog V4, V4MAIN01,
R828D**, and the Blog V4 driver path. The decoder uses 1090 MHz, 2.4 MS/s,
38.6 dB fixed gain, CRC correction disabled, verbatim Beast output, no Mode A/C
or network input, no bias tee, and no supplied receiver coordinates. Only the
Beast output is published by Docker, on `127.0.0.1:30005`. No feeder is installed.

The antenna's new vertical orientation is user supplied. Physical cable loss,
antenna match, filtering and amplification have not been measured. Initial
samples have zero reported drops, noise around -37.2 dBFS and zero strong-signal
counts, but **zero valid messages/aircraft** at the dated evidence snapshot.
Large rejected/candidate counts are not aircraft detections. These observations
do not establish a need for an LNA/filter or prove a usable antenna path. A
1090 MHz filter could help only if out-of-band overload is established; an LNA
could help a loss-limited system but can also worsen overload. No purchase,
hardware change or bias power is justified by this short observation alone.

## Scoped RF lease and restoration

[session.py](../adsb-session/session.py) inventories actual installed/loaded RF
units and USB sysfs identity/open file descriptors. Before the trial, the sole
USB owner was the scheduler's `rtl_fm`. An owner outside known capture unit
cgroups causes refusal. It never force-terminates an unknown owner.

Before pausing, it durably records every affected unit's ActiveState, SubState,
UnitFileState, exact start/expiry, and prior USB ownership. It adds only its own
`91-adsb-lease.conf` ConditionPathExists guard, then stops conflicting timers
before services. Enablement of existing RF units is unchanged. Actual live
conflicts included scheduler, health recovery, METEOR dispatcher/recovery and
legacy meteor/satellite capture/preflight paths; already-disabled standalone
receivers remain stopped. It holds the existing V4 advisory lock during capture.

The broad acquisition suspend API is deliberately not used: it also stops
processing unrelated to the SDR. Dashboard, ATIS processing/shadow, interpreter,
METEOR planning/processing, registration, shadow analysis and retention continue.
The existing dashboard has no added ADS-B panel and its broad acquisition status
does not represent this narrower lease. Historical dashboard data remains available.

The decoder supervisor checks the absolute UTC deadline and an initial monotonic
deadline. Every restart re-reads the same saved expiry; a clock before the saved
launch causes fail-closed abort. USB identity is resolved again after reboot.
The host clock was NTP-synchronized; its RTC is not a trustworthy wall clock.
There are six bounded capture attempts, 10-second restart delay, 90-second
listener-start bound and 120-second sample-progress bound. A successful empty
RF observation is not treated as a decoder failure.

Independent persistent `rf-watchkeeper-adsb-watchdog.timer` checks at UTC seconds
00/30 and 10 seconds after boot. It restores on expiry, abort or incomplete
preparation/restoration. Normal capture stops at its deadline; watchdog fallback
acts within approximately 30 seconds plus stop/start time. `ExecStopPost` removes
only the named ADS-B container even when the supervisor is killed. Docker itself
has no container restart policy.

Restoration stops/disables ADS-B, positively checks container release and USB
ownership, removes only these lease guards, reloads units, and starts only
previously active services/timers. It verifies active/inactive and enablement
against the saved inventory; inactive one-shots are not replayed manually.
Timers may naturally dispatch due jobs once resumed. Successful state evidence
and a database summary are archived, then the live lease is cleared. If release
or restoration fails, the lease remains for watchdog retry and errors are
logged. Missing USB/unknown ownership leaves the RF guard in place rather than
guessing. Persistent idle watchdog checks remain installed for future leases.

## Private records and bounds

All received data remains on the EVK under
`/root/rf-watchkeeper/adsb-session/private/` (0700, umask 0077), excluded from Git.
`aircraft.sqlite` is shared across sessions:

* `frames`: session, host receipt UTC, Beast type, original 12 MHz receiver ticks,
  RSSI byte, uncorrected payload hex, direct-address ICAO where available.
  Other Mode-S address/parity forms can have null ICAO in this table.
* `snapshots`: unchanged decoder aircraft/stats JSON with collection UTC. Decoded
  ICAO, callsign, altitude, speed, vertical rate, track and CPR position are kept
  whenever the decoder supplies them. Values/ages have their decoder semantics;
  receipt UTC is not a precise RF time-of-arrival measurement. No observer
  reference is supplied, so receiver-reference surface/local CPR is unavailable.
* `aircraft`: cross-session ICAO first/last seen, session count and latest original
  decoded aircraft object. Full historical snapshots are separate.
* `sessions`: session deadlines and decoder/driver provenance.

No IQ is recorded. Beast escapes are losslessly unescaped into the separate
ticks/signal/payload fields; the original message bits are retained. Invalid RF
candidates rejected by dump1090 are counted in diagnostics, not stored as aircraft.
Network heartbeats are disabled so they cannot inflate received-message counts.

The database and WAL have a combined **1 GiB stop threshold** (small polling/
transaction overshoot is possible), with a 2 GiB free-disk floor. Each session's
decoder log has a 16 MiB stop threshold. Reaching a bound ends capture early and
triggers restoration while retaining records. There is no destructive pruning;
future sessions also honor the shared database bound. Per-attempt JSON output
avoids stale counter reuse following restart. `health.json`, per-session
provenance/command, final summary and `changes.ndjson` retain diagnostics even
when no aircraft is received. The rest of the EVK's existing retention rules
are unchanged. Raw aircraft positions are private and must not be committed.

## Commands, installation and rollback

Only use after inspecting the actual unit inventory and current source. As root
on the EVK, with files at `/root/rf-watchkeeper/adsb-session`:

```sh
cd /root/rf-watchkeeper/adsb-session
docker build -t rf-watchkeeper-adsb:20261101 .
python3 -m unittest -v test_session
python3 session.py install
python3 session.py start --seconds 43200
```

Installation creates the three ADS-B service/timer files; it refuses collisions
with pre-existing lease guards. Do not overwrite unrelated units or use this on
an uninspected different installation. Read-only inspection:

```sh
systemctl status rf-watchkeeper-adsb.service rf-watchkeeper-adsb-watchdog.timer
cat private/lease.json
python3 audit.py
```

Early rollback is `python3 session.py restore`. Preserve the lease until that
command has restored and verified prior state. Never start the scheduler while
capture owns the SDR or manually erase the lease. To remove the feature after
restoration, disable/stop the watchdog timer, remove only the three generated
ADS-B unit files, reload systemd, and retain private data. No original RF source,
configuration or data was modified. Installation does not remove the image or
collected records. Frozen [verification](evidence/adsb-session-20261101/verification.json)
and [completion/limitations](evidence/adsb-session-20261101/completion.md) distinguish
trial verification from the ongoing 12-hour run.

## ADS-B Live and automatic health report — 1 November 2026

The existing dashboard links to `/adsb` on the same port 8080 and access scope.
`/api/adsb` exposes only the observer's limited status projection, with no
coordinates, trails, database download, raw frames or logs. Aircraft identity,
callsign, altitude, speed and last seen are available on the existing LAN scope.
No map or external notification/feeder transport was added. The page refreshes
every 12 seconds, shows health freshness, sample progress/drops, current-attempt
and total attempts, session-scoped frame/aircraft counts, last detection,
absolute Helsinki deadline/countdown, watchdog and explicit RF pause/restoration.
Empty reception, stale health, stalled decoder, failed supervisor and completed
session have distinct status. A browser flags monitor data older than 40 seconds.

The independent `rf-watchkeeper-adsb-monitor.service` runs `adsb-session/monitor.py`
every 12 seconds. It has no capture/watchdog/scheduler dependencies or service
control actions; private devices, read-only system protection, a 20% CPU quota
and 128 MiB memory limit bound its impact. Only the private ADS-B directory is
writable. SQLite connections use `mode=ro`, `query_only`, 100 ms busy timeout,
two-second execution budget, explicit close and 500-snapshot batches. No schema
or index changes. Cursor/aggregate state survives observer restart; while it
catches up the page labels counts provisional. Unique aircraft combines distinct
direct DF17 addresses with decoded addresses seen in this session's snapshots,
never the all-sessions registry. Decoder non-ICAO addresses keep their `~` marker.
Recent values retain decoder semantics and the last actual detection time.
Position presence is counted privately; coordinates never enter this API.

After the existing restorer archives successful restoration, the monitor saves
`private/<session>-health-summary.json`: session detections, attempts, sample
segments/drops, final health, read-only database quick_check, stop reason and
saved/current service restoration evidence. Observed receiver uptime is the sum
of per-segment sample totals divided by 2.4 MS/s. It is a lower bound: attempts
without stats snapshots and samples after the final snapshot are unmeasured;
attempt count comes from the saved lease. This is receiver sample time, not a
claim of RF coverage. Abort, restoration-in-progress or expiry overrun also saves
`private/<session>-health-alert.json`, with actionable state and integrity result.
On a completed run the dashboard displays report readiness, integrity, uptime,
samples, drops and restoration state. Reports remain local and private (0700
directory / 0077 umask). Failed integrity/restoration raises a dashboard alert.
The existing `<session>-summary.json` and restorer are unchanged. A subsequent
session is selected from the active lease; otherwise the latest restored session
is shown. No notification transport is assumed or activated.

Deployment preserved the existing dashboard's private runtime configuration;
public source continues to use approximate regional coordinates. The dashboard
was proven isolated (separate cgroup; no BindsTo, PartOf or stop propagation),
then restarted alone. Capture PID/start ticks, container ID/start time, attempt
count and exact expiry were equal before/after. Neither capture nor watchdog
nor RF scheduler was stopped, restarted or reconfigured by this change.

### Rollback and persistence

Private originals and deployment evidence are under
`private/monitor-deployment-20261101/`. To roll back monitoring only, stop/disable
`rf-watchkeeper-adsb-monitor.service`, restore that directory's dashboard.py and
dashboard.html, and restart **only** the independently isolated dashboard.
Retain private reports and aircraft data. Never invoke capture restore/restart
or manually start RF services to roll back this UI. The new observer is enabled
for boot; its restart preserved aggregates in live checks. Full EVK reboot and
the actual 12-hour completion remain unverified during the active reservation.
The expiry remains 2 November 2026 07:00:45.977 UTC / 09:00:45 Helsinki.

Validation: seven ADS-B fixture/regression tests and 25 existing dashboard,
capacity, RF-health, AIS and acquisition-control tests passed. Fixture tests
cover completed/empty/stale/early-abort paths, session isolation, coordinate
omission, read-only enforcement and private reports. Live HTTP/browser checks
showed advancing samples, zero reported drops, two aircraft and decoded position
presence; no aircraft identities/positions are published in evidence. Four
private database/state/log paths returned 404. Full unattended completion and
boot persistence are outstanding observations, not passed tests.


## ADS-B aircraft map and fixed light theme — 1 November 2026

Supersedes the earlier coordinate-omission statement for the new map endpoint.
`/adsb` now has a locally served Leaflet 1.9.4 interactive map, fixed light
colors, keyboard zoom/pan, fit-aircraft control and sanitized aircraft popups.
The linked dashboard's remaining dark schedule header and suspension banner
are light too; browser/system dark preferences are not adopted.

`/api/adsb/positions` projects only decoded public aircraft fields from the
selected session. SQLite is read-only/query-only with 100 ms busy timeout and
500 ms execution budget. It examines at most the latest 5000 stored rows,
2 MB of JSON, 500 aircraft per snapshot and returns at most 100 positions;
results are cached for 10 seconds. Query parameters are rejected (400), so no
unbounded history request or pagination bypass is available. No database/schema,
observer, capture, watchdog, expiry or RF configuration changes were made.

Fresh positions require a decoder `seen_pos` age, at most 60 seconds since the
actual position report, active receiver, fresh monitor and health, and an
unfinished session. Unknown-age positions are historical. Grey historical last
known positions are optional/off by default and limited to that bounded scan;
this is incomplete history, not replay/tracks or a coverage claim. No movement
is invented. Last-seen time and position time are separate; missing altitude,
speed or heading remains unavailable. Callsign can come from the same session's
identity projection. CPR decoding remains dump1090's responsibility with no
receiver reference supplied. No receiver pin, receiver coordinates, private
metadata, automatic geolocation, raw snapshots or external feeder is exposed.

The 12-second refresh remains; fetches time out after five seconds. Browser
freshness checks demote cached positions when disconnected. Empty maps never
center on a receiver. Optional OpenStreetMap tiles require a click after a
visible privacy explanation (viewer IP and visible aircraft area reach the tile
provider); attribution stays visible. Leaflet and its BSD-2-Clause license are
vendored locally; tiles use normal browser caching and no prefetch/offline bulk
download. [Leaflet source](https://leafletjs.com/download.html) and
[OSM tile policy](https://operations.osmfoundation.org/policies/tiles/).

Validation at 19:35 UTC / 21:35 Helsinki: 296 valid frames, two session aircraft,
zero fresh positions, two genuine historical markers, advancing samples and
zero reported drops. Desktop 1280x1000 and mobile 390x844 browser checks verified
light appearance, both historical markers, fit control, popup identity/times,
attribution and no mobile page overflow. Live unavailable state was observed
during the isolated dashboard restart and recovered on refresh. Fresh/empty,
unknown-age, invalid coordinates, completed session, stale monitor, session
isolation and scan bounds are fixture-tested; no fresh live aircraft happened
to be present during browser verification. Private DB/state/log routes return
404; arbitrary position-query parameters return 400. Five cached position
requests took 0.009 seconds. See [verification](evidence/adsb-map-light-20261101/verification.json)
and [completion](evidence/adsb-map-light-20261101/completion.md).

Only the dashboard service was restarted after checking its independent cgroup,
empty PartOf/BindsTo/PropagatesStopTo relationships. Capture PID/start ticks,
container ID/start time, attempt count (3), deadline and watchdog activation
were unchanged. Final capture identity also matched the earlier 19:18 dashboard
deployment evidence. The end remains 2 November 09:00:45 Helsinki.

Rollback: private originals are in
`adsb-session/private/map-light-deployment-20261101/`. Restore dashboard.py,
dashboard.html and adsb.html from there, then restart only the isolated dashboard.
The additional module/assets may remain unused; retain aircraft records and
monitor reports. Never restart capture/watchdog or invoke RF restoration for UI
rollback. Dashboard restart persistence is verified; full EVK reboot and actual
unattended session expiry/restoration remain unverified during capture.

Position projection runs in an isolated Python worker (two-second parent timeout),
cached for ten seconds, so busy dashboard threads cannot consume its SQLite
execution budget. This corrected a final-check contention timeout.
