> Documentation status, 2026-10-05: Historical October 3 installation guide. Current automation is enabled, cleanup disabled, and live/future managed sample rate 256000. Recovery and partial-success handling have evolved; see [METEOR](docs/meteor.md), [reliability](docs/reliability.md) and [project log](docs/project-log.md). Do not apply historical defaults as current configuration.

# RF Watchkeeper METEOR milestone 1

Prepared 2026-10-03 for Thomas Vikström. The current configuration runs the entire workflow on the EVK, including isolated ARM64 SatDump processing; no Dell is needed. See `AUTONOMOUS_EVK.md` for runtime details. Installation is additive and disabled. Existing `satellite_capture.py`, planner, jobs, manual reservations and unrelated services are unchanged. The EVK has no Git checkout or Git executable; the GitHub repository is empty. The local review bundle and install manifest provide review and rollback without publishing a repository.

## Components

- `meteor_pipeline.py`: uses the live planner's TLE loader and predictor; enforces TLE NORAD identity and at most three days between epoch and the entire planning window. Plans complete 10-degree passes over 36 hours, minimum peak 25 degrees, at least 60 seconds within azimuth 120–240 degrees. Ranks by time in the south sector then peak elevation; limits to four nonoverlapping passes per Helsinki calendar day including previously attempted automatic passes and known upcoming manual METEOR timers. It never cancels manual passes, even when they exceed that limit.
- Recorder wrapper: preserves existing recorder CLI and behavior, explicitly selects V4MAIN01, 137.9 MHz, 1.024 MS/s, gain 49.6 dB, 90-second margins and 120-second preflight. Does not call the existing standalone preflight service, which contains a reboot action. No reboot path exists in this addition.
- Persistent JSON plan/attempt state under `/root/rf-watchkeeper/data/meteor-auto`. Stable UTC pass IDs, atomic state writes, locks, capture/decode logs, structured events and extension fields `score`, `analysis`, `notification`.
- Existing manual `meteor-*`/`satellite-*` timers take priority. Their capture windows are read from unit definitions, with a conservative 45-minute reservation fallback. Active/manual recorder processes defer automation. Unsynchronized clock, stale plan, insufficient storage, existing files or an intentionally stopped V4 scheduler prevent capture.
- `meteor-auto-capture.service`: bounded recorder wrapper, complete process-group termination and `ExecStopPost` recovery. Missed/interrupted captures are not automatically replayed. Boot recovery restores the V4 scheduler only for a recorded pipeline capture interruption; manual recordings defer recovery.
- Four EVK timers: hourly planning, 30-second dispatch checks, five-minute decoder queue, daily opt-in retention. Planning and retention calendar timers persist catch-up across reboots. Monotonic dispatch and processing timers start again after boot. Recovery is a boot service.
- `satdump_evk.py`: bounded ARM64 container decoder with pinned image identity, read-only IQ, limited writable outputs, no network/SDR access and explicit owned-container cleanup. Docker was already active and enabled on the EVK; its host service was not changed. The process unit declares its runtime dependency for boot ordering.
- The old Dell worker remains only as an optional development reference. Its disabled Windows task has been removed and the primary configuration does not use it.

`satdump_command` selects the EVK wrapper through the existing satellite Python. `satdump_prefix` is empty for the installed SatDump 1.2.2 legacy CLI; newer SatDump versions may require `["pipeline"]`. The default pipeline is `meteor_m2-x_lrpt`, raw format `cu8`, metadata sample rate, DC blocking, and explicit M2-3/M2-4 selection. This is actual unsigned RTL-SDR raw IQ; earlier signedness experiments with SDR#/RF64 WAV are separate. See the [official SatDump CLI documentation](https://docs.satdump.org/index.html).

## Safe inspection and tests

EVK, after disabled installation:

```sh
cd /root/rf-watchkeeper
.satellite-venv/bin/python meteor_pipeline.py plan --dry-run
.satellite-venv/bin/python meteor_pipeline.py status
.satellite-venv/bin/python meteor_pipeline.py cleanup
.satellite-venv/bin/python meteor_pipeline.py worker-list --dry-run
.satellite-venv/bin/python -m unittest discover -s /root/rf-watchkeeper/meteor-stage-20261003 -p test_meteor_pipeline.py
```

`plan --dry-run` predicts using the existing planner and may refresh its existing TLE cache, but does not save a plan, enable timers, run preflight or access the SDR. Status reads saved selections and processing states. `cleanup` prints eligible deletions without deleting; `cleanup --apply` requires `cleanup_enabled: true`. Cleanup scans only owned successful attempts, requires the exact generated raw path and original file identity (device, inode, byte count and modification time), rejects symlinks and replaced files, respects `"hold": true`, retains raw for fourteen days, and preserves metadata, logs and all decoder artifacts. Failed/interrupted/unprocessed passes and all older manual captures are preserved. This can fill storage; the disk-headroom gate then skips captures rather than deleting unknown files.

For one queued EVK decode, run `meteor_pipeline.py process`; it never opens an SDR. For an offline decode, copy the pass record into a verification folder, then use `meteor_pipeline.py decode --record <copy> --iq <existing-iq> --output <new-output-directory>`. Existing output directories are never overwritten. Missing/changed runtime images leave the queue intact.

## Enable only after reviewing the selected passes

1. Review `plan --dry-run`, status, manual reservations and free storage. Defaults require ten GiB remaining after the estimated recording. Status checks the pinned EVK decoder image as well as its executable.
2. In EVK `/root/rf-watchkeeper/meteor-config.json`, set `enabled` to `true`; keep `cleanup_enabled` false initially. Enabling capture does not enable deletion.
3. Run:

```sh
systemctl enable rf-watchkeeper-meteor-recover.service
systemctl start rf-watchkeeper-meteor-recover.service
.satellite-venv/bin/python meteor_pipeline.py plan
systemctl enable --now rf-watchkeeper-meteor-plan.timer rf-watchkeeper-meteor-dispatch.timer rf-watchkeeper-meteor-process.timer rf-watchkeeper-meteor-cleanup.timer
```

4. Monitor `journalctl -u meteor-auto-capture.service`, `journalctl -u rf-watchkeeper-meteor-dispatch.service`, `journalctl -u rf-watchkeeper-meteor-process.service`, `data/meteor-auto/events.jsonl`, each pass's `pass.json`, `capture.log` and decoder `satdump.log`. Decoding failures retry at most three times with an hour delay, then remain for review. Image file presence is recorded, not treated as proof of good imagery. No computer login is needed.

## Disable and roll back

Set `enabled` false and disable the four timers. Let any active capture finish before rollback. Do not stop unrelated services.

```sh
systemctl disable --now rf-watchkeeper-meteor-plan.timer rf-watchkeeper-meteor-dispatch.timer rf-watchkeeper-meteor-process.timer rf-watchkeeper-meteor-cleanup.timer
python3 /root/rf-watchkeeper/meteor-stage-20261003/install_meteor.py rollback
```

The installer validates hashes before removal, preserves modified configuration in a dated backup, and refuses to remove unexpectedly modified code/unit files. It removes only its recorded additions; raw recordings, processed products, attempt metadata, logs and stage are preserved. Installation touched no preexisting recorder/scheduler file, so there is no recorder/scheduler patch to revert. The isolated Docker image/runtime manifest remain recoverable artifacts; see `AUTONOMOUS_EVK.md`.

## Remaining validation and next milestone

No full live capture is run during installation; the current manual passes remain authoritative. The first enabled automatic pass must validate capture handoff and EVK post-processing together. Simulated failure tests and offline SatDump runs do not establish unattended RF reception reliability. Native EVK decoding is now the primary path and needs no Dell.

Next: extract objective sync/BER/decoded-line/continuity measurements, compare frequency-shift trials, and decide meaningful quality/keep rules. Add AI analysis and email through the existing extension fields after the core pipeline has produced repeatable results. There is no AI or email dependency in this milestone.
