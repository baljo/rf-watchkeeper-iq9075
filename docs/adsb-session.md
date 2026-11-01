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
