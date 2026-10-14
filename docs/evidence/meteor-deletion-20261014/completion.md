# Production METEOR automatic raw deletion — 14 October 2026

Observed 17:36–17:40 UTC / 20:36–20:40 EEST. Explicit user authorization enables ongoing automatic deletion. Both authoritative `meteor-config.json` gates are now true: `cleanup_enabled` and `retention.automatic_deletion_validated`. No other configuration value changed (full private before/after config remains on EVK).

## Dry-run before timer restart

| Disposition | Existing raws | Bytes |
|---|---:|---:|
| PROTECTED | 18 | 11703156736 |
| GRACE | 1 | 419430400 |
| DELETABLE | 25 | 10417864704 |
| REVIEW | 5 | 3293052928 |

All 25 candidates passed capture-completion, unchanged fingerprint, valid size, clean decoding and supported nominal/offset procedure checks; all were no-signal, without useful products or explicit protection. No classification errors. `cleanup --dry-run` performed no deletion. These exact candidates were then deleted by one controlled `systemctl start rf-watchkeeper-meteor-cleanup.service` invocation after enabling the existing timer.

| Eligible and actually deleted raw basename | Bytes |
|---|---:|
| `M2-3_20261005_182723_137900000.cu8` | 421265408 |
| `M2-3_20261006_081137_137900000.cu8` | 416284672 |
| `M2-3_20261006_180412_137900000.cu8` | 418119680 |
| `M2-3_20261007_074824_137900000.cu8` | 406061056 |
| `M2-3_20261008_090509_137900000.cu8` | 417333248 |
| `M2-3_20261008_185748_137900000.cu8` | 416808960 |
| `M2-3_20261009_084153_137900000.cu8` | 420216832 |
| `M2-3_20261009_183425_137900000.cu8` | 420741120 |
| `M2-3_20261010_081838_137900000.cu8` | 418381824 |
| `M2-3_20261010_181111_137900000.cu8` | 419954688 |
| `M2-3_20261011_075524_137900000.cu8` | 409993216 |
| `M2-3_20261012_091211_137900000.cu8` | 415236096 |
| `M2-3_20261013_084854_137900000.cu8` | 419954688 |
| `M2-4_20261006_012650_137900000.cu8` | 405536768 |
| `M2-4_20261006_130029_137900000.cu8` | 409468928 |
| `M2-4_20261007_024516_137900000.cu8` | 419954688 |
| `M2-4_20261007_123833_137900000.cu8` | 418906112 |
| `M2-4_20261008_022335_137900000.cu8` | 422051840 |
| `M2-4_20261008_121646_137900000.cu8` | 422838272 |
| `M2-4_20261009_115507_137900000.cu8` | 422313984 |
| `M2-4_20261010_014017_137900000.cu8` | 412614656 |
| `M2-4_20261011_011841_137900000.cu8` | 399245312 |
| `M2-4_20261012_023704_137900000.cu8` | 421003264 |
| `M2-4_20261012_123019_137900000.cu8` | 420741120 |
| `M2-4_20261013_120835_137900000.cu8` | 422838272 |

Total: **25 raws / 10,417,864,704 bytes** (9.702392578125 GiB). Remaining **24 raws / 15,415,640,064 bytes**: PROTECTED 18 / 11,703,156,736; GRACE 1 / 419,430,400; REVIEW 5 / 3,293,052,928; DELETABLE 0 / 0. Counts are frozen observations.

## Policy and safeguards

No-signal grace remains >=24 h; poor/partial/synchronized grace >=48 h from capture completion. Useful/reference/regression/imported/historical-useful captures stay protected indefinitely. Errors, incomplete evidence and partial/synchronized evidence after grace stay REVIEW. Zero-byte failed captures now also stay REVIEW. Partial lines/products and errors from earlier attempts are checked, rather than only the selected attempt. Top-level imported provenance and database regression/pin/protection flags are respected. Disk pressure never overrides grace/protection. Cleanup is restricted to eligible owned `recordings/satellite/*.cu8`; metadata, images, attempts and history remain.

The timer alone was disabled/stopped during edits. Capture/processing were not stopped or restarted. Shared capture/processing/retention locks and raw fingerprint/open-reader safeguards remain. Capture's existing low-disk entry point also uses the same gates and classifier; the timer is not the only possible automatic invocation.

## Verification and commands

Read deployed AGENTS/workflow, current-status, operations, METEOR/data-retention guides, config, `meteor_retention.py`, `meteor_frequency.py`, cleanup timer/service/drop-in and service state. Preserved files under `backups/meteor-deletion-20261014/` on EVK; `*.original` are untouched runtime source/test baselines. Initial copied source names in that backup directory were later used for staged replacements; use `.original` for rollback.

Commands (in `/root/rf-watchkeeper`, Python `.satellite-venv/bin/python`):

```sh
systemctl disable --now rf-watchkeeper-meteor-cleanup.timer
.satellite-venv/bin/python meteor_pipeline.py cleanup --dry-run
.satellite-venv/bin/python -m unittest test_meteor_retention test_meteor_history test_meteor_recovery test_satellite_import
systemctl enable --now rf-watchkeeper-meteor-cleanup.timer
systemctl start rf-watchkeeper-meteor-cleanup.service
.satellite-venv/bin/python meteor_pipeline.py cleanup --dry-run
systemctl list-timers --all rf-watchkeeper-meteor-cleanup.timer
systemctl show rf-watchkeeper-meteor-cleanup.service -p Result -p ExecMainStatus
```

Initial 141 regression test executions passed (including inherited repeats); the final focused suite passed **101 tests**. [Final test output](tests-final.txt). Recovery/device operations in tests were mocked; no actual RF reset/reboot. [Exact tests](tests.txt), [source patch](changes.patch), [sanitized verification](verification.json). Private inventory, preservation manifests and maintenance journal remain in the EVK backup directory.

Controlled service run: Result=success, ExecMainStatus=0. Timer enabled/active/waiting, daily 02:00 UTC plus existing OnUnitActiveSec=15min; next observed run 2026-10-14 17:54:24 UTC / 20:54:24 EEST. Effective ExecStart remains `.satellite-venv/bin/python -u /root/rf-watchkeeper/meteor_pipeline.py maintenance`, oneshot, working directory project root, timeout 120 s, UMask 0077. Unit/drop-in scheduling unchanged; historical comment saying deletion gated off is superseded by this policy.

Preservation manifests found no missing nonraw files and no changed nonraw content except appended retention-events.jsonl after excluding intended retention fields. Database preexisting history content (excluding retention/projection fields) and complete image rows unchanged. All 25 actual missing raw names match exactly the dry-run candidates and audit; no additional raw removed. Plan/dispatch/process/legacy-register timers active; capture/process oneshots idle with last Result=success/exit 0; scheduler/dashboard active. No capture/process restart needed. Final verification confirmed all **254 indexed image files exist**, all 46 database pass records remain, only the two config gates changed, and the 25 durable deletion events match exact candidate names/bytes. [Final assertions](final-check.json).

## Rollback and completion checks

Disable/stop cleanup timer; under shared locks set both gates false atomically (or restore saved original `meteor-config.json` after confirming no unrelated config change); retain stricter classifier. Restore `.original` source/test only if rolling back code, with gates false. Re-enable existing timer for nondeleting maintenance if desired. Deleted raw IQ cannot be restored; metadata/history/images survive.

Definition of Done: live inspected; exact sanitized changes and private full config backup saved; tests/commands/results recorded; dated shared log/current-status/operations/architecture updated; rollback documented; live counts dated; location privacy checked; unrelated production decisions preserved. Implemented, tested, deployed and production-active; controlled real maintenance execution verified, followed by a second successful zero-deletion maintenance run. Timer enablement survives service restarts by persistent config and enabled symlink. Reboot and later unattended timer-cycle validation remain **unverified**; no disruptive reboot or RF service restart was performed. Native SatDump SIGSEGV and bounded-search/indoor-reception limitations remain unchanged. Git publication is recorded by the task's final commit receipt.

The final correction also preserves the 48-hour grace for partial products in any earlier attempt and carries original managed reference/regression/imported protections into review records. The cleanup timer was briefly paused again for this correction; final dry-run had zero candidates before resuming and a second maintenance run deleted zero additional raws.
