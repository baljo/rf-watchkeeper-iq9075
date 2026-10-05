# METEOR retention dry-run correction — 5 October 2026

Inventory frozen at 2026-10-05T20:55:46.678466+03:00 (Europe/Helsinki). **Zero raw IQ files deleted; both real deletion gates remain disabled.**

All satellite raw: 31 files / 30,039,343,104 bytes. METEOR subset: 30 files / 29,979,836,416 bytes.

| Group | Files | Exact bytes | GB (decimal) | GiB |
|---|---:|---:|---:|---:|
| PROTECTED | 9 | 7,986,741,248 | 7.986741248 | 7.438232422 |
| GRACE | 2 | 840,171,520 | 0.840171520 | 0.782470703 |
| DELETABLE | 18 | 19,179,241,472 | 19.179241472 | 17.862060547 |
| REVIEW | 2 | 2,033,188,864 | 2.033188864 | 1.893554688 |
| all_satellite_raw | 31 | 30,039,343,104 | 30.039343104 | 27.976318359 |
| METEOR | 30 | 29,979,836,416 | 29.979836416 | 27.920898438 |
| above_1_GiB | 15 | 24,540,872,704 | 24.540872704 | 22.855468750 |
| sample_rate_256000 | 14 | 5,339,873,280 | 5.339873280 | 4.973144531 |
| sample_rate_1024000 | 16 | 24,600,379,392 | 24.600379392 | 22.910888672 |
| sample_rate_unknown | 1 | 99,090,432 | 0.099090432 | 0.092285156 |
| explicit_reference | 4 | 980,156,416 | 0.980156416 | 0.912841797 |
| protected_or_reference | 9 | 7,986,741,248 | 7.986741248 | 7.438232422 |
| no_image | 24 | 20,999,569,408 | 20.999569408 | 19.557373047 |
| failed_or_no_image | 31 | 30,039,343,104 | 30.039343104 | 27.976318359 |

Dry-run reclaimable: **18 files / 19,179,241,472 bytes / 17.862060547 GiB**. Actual reclaimed: **0 bytes**. Groups overlap where indicated by their meaning; they must not be added together.

## What changed

Historical raw is now included rather than automatically treated as unmanaged/reference. Disabled gates do not suppress eligibility. A failed/no-image result gets finite capture-completion grace; completing the current supported nominal and offset workflow can make old no-image material eligible without claiming exhaustive proof that no signal exists. Genuine errors, incomplete evaluation and ambiguous partial/synchronized evidence require review. Useful products from any attempt, including crashes and newly recovered historical products, remain protected.

Existing durations retained: 24h no-image, 48h partial. The anchor deliberately changes from latest evaluation to capture completion, preventing indefinite extension by repeated attempts. Useful-image captures are protected. Explicit references are listed with reasons in the exact inventory.

Offset handling uses the existing 24-window ±60 kHz survey, two ranked candidate corrections and native SatDump at the saved recording sample rate. No raw/capture sample-rate change was made. The bounded procedure can miss weak/out-of-span/drifting signals; its completion is a policy prerequisite, not proof of absence. Known unused plugin/TLE-network notices are distinguished from decoding failures only when processing completion markers exist.

## Dry-run candidate list

| Filename | Bytes | GiB | Applied shifts (Hz) | Reason |
|---|---:|---:|---|---|
| M2-3_20260929_220706_137900000.cu8 | 410,517,504 | 0.382324219 | [0, -32500, -17500] | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-3_20260930_115106_137900000.cu8 | 417,333,248 | 0.388671875 | [0, -17500, -32500] | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-3_20260930_200427_137900000.cu8 | 1,548,746,752 | 1.442382812 | [0, -12500, -27500] | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-3_20261001_212022_137900000.cu8 | 1,675,624,448 | 1.560546875 | [0, 60000, 7500] | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-3_20261002_110436_137900000.cu8 | 1,646,788,608 | 1.533691406 | [0, 60000, 45000] | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-3_20261003_122125_137900000.cu8 | 1,640,759,296 | 1.528076172 | [0, 60000, 45000] | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-3_20261003_203413_137900000.cu8 | 1,622,409,216 | 1.510986328 | [0, 60000, 45000] | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-3_20261004_115807_137900000.cu8 | 416,284,672 | 0.387695312 | [0, 45000, 60000] | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20260929_051817_137900000.cu8 | 420,741,120 | 0.391845703 | [0, -7500, 7500] | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20260929_150958_137900000.cu8 | 0 | 0.000000000 | [] | Expired failed capture contains zero IQ samples; history retained |
| M2-4_20260930_045637_137900000.cu8 | 416,808,960 | 0.388183594 | [0, -20000, -35000] | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20260930_144950_137900000.cu8 | 1,679,294,464 | 1.563964844 | [0, -22500, -37500] | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20261001_142820_137900000.cu8 | 1,654,915,072 | 1.541259766 | [0, 30000, 45000] | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20261001_160849_137900000.cu8 | 1,607,729,152 | 1.497314453 | [0, 22500, 37500] | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20261002_041325_137900000.cu8 | 1,575,223,296 | 1.467041016 | [0, 60000, 45000] | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20261002_140657_137900000.cu8 | 402,915,328 | 0.375244141 | [0, 55000, 40000] | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20261002_154649_137900000.cu8 | 1,657,012,224 | 1.543212891 | [0, 60000, 45000] | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20261004_065024_137900000.cu8 | 386,138,112 | 0.359619141 | [0, 50000, 35000] | Capture grace expired; supported current nominal and offset procedure produced no useful images |

## Files requiring review

| Filename | Bytes | Reason |
|---|---:|---|
| M2-3_20260928_223042_137900000.cu8 | 398,721,024 | Decoder error or interrupted offset search needs review: selected returncode=139; Nominal processing failed; preserve IQ and normal bounded retry behavior |
| M2-4_20261001_043500_137900000.cu8 | 1,634,467,840 | Decoder error or interrupted offset search needs review: selected returncode=139; Nominal processing failed; preserve IQ and normal bounded retry behavior |

## Complete inventory

| Filename | Satellite / saved pass time | Sample rate (S/s) | MiB | GiB | Age (days) | State | Images | Explicit reference | Reason |
|---|---|---:|---:|---:|---:|---|---|---|---|
| M2-3_20260928_223042_137900000.cu8 | M2-3 / 2026-09-28T22:32:12+03:00 | 256000 | 380.250 | 0.371337891 | 6.92501 | REVIEW | yes | no | Decoder error or interrupted offset search needs review: selected returncode=139; Nominal processing failed; preserve IQ and normal bounded retry behavior |
| M2-3_20260929_202718_137900000.cu8 | M2-3 / 2026-09-29T20:28:48+03:00 | 256000 | 382.750 | 0.373779297 | 6.01063 | PROTECTED | none in saved/current evidence | yes | Documented native-decoder regression and frequency-offset troubleshooting reference (historical-cleanup-20261005/report.md) |
| M2-3_20260929_220706_137900000.cu8 | M2-3 / 2026-09-29T22:08:36+03:00 | 256000 | 391.500 | 0.382324219 | 5.94112 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-3_20260930_115106_137900000.cu8 | M2-3 / 2026-09-30T11:52:36+03:00 | 256000 | 398.000 | 0.388671875 | 5.36874 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-3_20260930_200427_137900000.cu8 | M2-3 / 2026-09-30T20:05:57+03:00 | 1024000 | 1477.000 | 1.442382812 | 5.02683 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-3_20261001_212022_137900000.cu8 | M2-3 / 2026-10-01T21:21:52+03:00 | 1024000 | 1598.000 | 1.560546875 | 3.97340 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-3_20261002_110436_137900000.cu8 | M2-3 / 2026-10-02T11:06:06+03:00 | 1024000 | 1570.500 | 1.533691406 | 3.40117 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-3_20261002_223753_137900000.cu8 | M2-3 / 2026-10-02T22:39:23+03:00 | 1024000 | 1498.500 | 1.463378906 | 2.92015 | PROTECTED | yes | no | Useful channel products preserved, including historical/crash outputs |
| M2-3_20261003_122125_137900000.cu8 | M2-3 / 2026-10-03T12:22:55+03:00 | 1024000 | 1564.750 | 1.528076172 | 2.34786 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-3_20261003_203413_137900000.cu8 | M2-3 / 2026-10-03T20:35:43+03:00 | 1024000 | 1547.250 | 1.510986328 | 2.00574 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-3_20261003_221412_137900000.cu8 | M2-3 / 2026-10-03T22:15:42+03:00 | 256000 | 389.750 | 0.380615234 | 1.93623 | PROTECTED | yes | no | Useful channel products preserved, including historical/crash outputs |
| M2-3_20261004_115807_137900000.cu8 | M2-3 / 2026-10-04T11:59:37+03:00 | 256000 | 397.000 | 0.387695312 | 1.36389 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-3_20261005_083451_137900000.cu8 | M2-3 / 2026-10-05T08:36:21.699359+00:00 | 256000 | 400.750 | 0.391357422 | 0.38001 | GRACE | none in saved/current evidence | no | Finite capture-completion grace period has not expired |
| M2-3_manual_20260928_2112_137900000.cu8 | M2-3 (manual filename) / unknown | unknown | 94.500 | 0.092285156 | 6.99494 (mtime) | PROTECTED | none in saved/current evidence | yes | Explicit manual decoder reference; incomplete capture metadata |
| M2-4_20260929_051817_137900000.cu8 | M2-4 / 2026-09-29T05:19:47+03:00 | 256000 | 401.250 | 0.391845703 | 6.64147 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20260929_150958_137900000.cu8 | M2-4 / 2026-09-29T15:11:28+03:00 | 256000 | 0.000 | 0.000000000 | 6.22847 | DELETABLE | none in saved/current evidence | no | Expired failed capture contains zero IQ samples; history retained |
| M2-4_20260930_045637_137900000.cu8 | M2-4 / 2026-09-30T04:58:07+03:00 | 256000 | 397.500 | 0.388183594 | 5.65659 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20260930_144950_137900000.cu8 | M2-4 / 2026-09-30T14:51:20+03:00 | 1024000 | 1601.500 | 1.563964844 | 5.24457 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20261001_043500_137900000.cu8 | M2-4 / 2026-10-01T04:36:30+03:00 | 1024000 | 1558.750 | 1.522216797 | 4.67180 | REVIEW | yes | no | Decoder error or interrupted offset search needs review: selected returncode=139; Nominal processing failed; preserve IQ and normal bounded retry behavior |
| M2-4_20261001_142820_137900000.cu8 | M2-4 / 2026-10-01T14:29:50+03:00 | 1024000 | 1578.250 | 1.541259766 | 4.25964 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20261001_160849_137900000.cu8 | M2-4 / 2026-10-01T16:10:19+03:00 | 1024000 | 1533.250 | 1.497314453 | 4.19013 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20261002_041325_137900000.cu8 | M2-4 / 2026-10-02T04:14:55+03:00 | 1024000 | 1502.250 | 1.467041016 | 3.68712 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20261002_140657_137900000.cu8 | M2-4 / 2026-10-02T14:08:27+03:00 | 256000 | 384.250 | 0.375244141 | 3.27473 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20261002_154649_137900000.cu8 | M2-4 / 2026-10-02T15:48:19+03:00 | 1024000 | 1580.250 | 1.543212891 | 3.20513 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20261003_053146_137900000.cu8 | M2-4 / 2026-10-03T05:33:16+03:00 | 1024000 | 1601.750 | 1.564208984 | 2.63212 | PROTECTED | yes | no | Useful channel products preserved, including historical/crash outputs |
| M2-4_20261003_152459_137900000.cu8 | M2-4 / 2026-10-03T15:26:29+03:00 | 1024000 | 1603.750 | 1.566162109 | 2.22015 | PROTECTED | yes | no | Useful channel products preserved, including historical/crash outputs |
| M2-4_20261004_065024_137900000.cu8 | M2-4 / 2026-10-04T06:51:54+03:00 | 256000 | 368.250 | 0.359619141 | 1.57827 | DELETABLE | none in saved/current evidence | no | Capture grace expired; supported current nominal and offset procedure produced no useful images |
| M2-4_20261004_150317_137900000.cu8 | M2-4 / 2026-10-04T15:04:47+03:00 | 256000 | 400.750 | 0.391357422 | 1.23521 | PROTECTED | none in saved/current evidence | yes | Documented weak/poor reception regression reference (historical-cleanup-20261005/report.md) |
| M2-4_20261005_014827_137900000.cu8 | M2-4 / 2026-10-05T01:49:57.513173+00:00 | 1024000 | 1588.250 | 1.551025391 | 0.66233 | PROTECTED | yes | no | Useful channel products preserved, including historical/crash outputs |
| M2-4_20261005_114142_137900000.cu8 | M2-4 / 2026-10-05T11:43:12.821852+00:00 | 256000 | 400.500 | 0.391113281 | 0.25026 | GRACE | none in saved/current evidence | no | Finite capture-completion grace period has not expired |
| V4-VERIFY_20260930_193204_137900000.cu8 | V4-VERIFY / 2026-09-30T19:32:04+00:00 | 1024000 | 56.750 | 0.055419922 | 4.93273 | PROTECTED | none in saved/current evidence | yes | Explicit V4 hardware verification/reference recording |

Manual reference sample rate/pass timestamp are unknown because recording JSON is absent; its displayed age uses file mtime, explicitly identified above. Other ages use capture completion. “No images” does not assert exhaustive absence of signal.

## Verification

- zero_raw_files_deleted: True
- raw_fingerprints_unchanged: True
- capture_sidecars_unchanged: True
- capture_configuration_scheduler_sources_unchanged: True
- original_db_history_preserved: True
- original_db_image_rows_preserved: True
- deletion_gates_disabled: True
- large_files_all_1024ksps: True
- systemd_unit_files_unchanged: True
- boot_id_unchanged_during_deployment: True
- operational_timers_and_services_healthy: True
- future_planner_rates_unchanged: True
- dashboard_api_ok: True

Tests: Ran 84 tests in 0.462s  OK
Dashboard script syntax check passed. All retention test deletions are hypothetical/intercepted; no raw test IQ was deleted by the new retention suite.
Planner/dispatch/process/cleanup/registration services report success; corresponding timers, health timer, RF scheduler and dashboard are active. The pre-existing unrelated Qualcomm rmtfs.service failure is recorded separately; no new failed units were introduced.
Original recording JSON, raw fingerprints, capture configuration/scheduler source hashes, database history and existing image rows are preserved. New review records/logs/PNG products/evaluation DB are retained. Retention refresh may add/update policy fields without replacing original history.
No reboot, RF retune, capture-rate change or scheduler/timer changes were performed. Dashboard-only restart loaded the updated classifier/UI. The next action is review of the candidate list; actual deletion is not authorized.
