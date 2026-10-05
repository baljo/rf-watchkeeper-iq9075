# Historical METEOR cleanup review — 2026-10-05

Result: no raw IQ was deleted. The authoritative dry run has no eligible candidates and deletion remains disabled. Disk reduction could not safely proceed under the implemented policy.

- Satellite directory: 31 raw files, 30,039,343,104 bytes (27.976 GiB).
- METEOR subset: 30 raw files, 29,979,836,416 bytes.
- Proposed/deleted: 0 files; proposed/actual recovery: 0 bytes.
- Filesystem free before: 61,030,146,048 bytes; after review: 61,029,548,032 bytes. Small change is ordinary activity plus preserved evaluation/report evidence, not recovered space.

## Policy and self-review

Installed `meteor_retention.py` and `meteor-config.json` are authoritative. no_signal=24h, poor=48h, useful=168h from latest verified evaluation, not file age; free thresholds 20/10 GiB. `cleanup_enabled=false` and `automatic_deletion_validated=false`. Failed/unverified/pinned/excellent records are protected; unmanaged/reference IQ is outside automatic cleanup. No thresholds, flags, decoder settings, schedules, services, or dashboard were changed. The user additionally requires permanent preservation of useful-image captures.

The sole zero-byte IQ `M2-4_20260929_150958_137900000.cu8` has status failed_no_iq and contains no samples. It would recover zero bytes; the installed cleanup has no failed-capture deletion branch. It is retained rather than introducing an independent unlink rule. Missing raw for other failed passes is pre-existing, not a deletion in this review.

## Proposed deletion table

| Filename | Satellite/pass time | Size | Classification | Image/decode result | Current frequency evaluation completed | Reason | Recovery |
|---|---|---:|---|---|---|---|---:|
| None | — | 0 | No eligible candidates | — | — | Authoritative policy protects all existing candidates | 0 |

## Current decoder check

`M2-3_20260929_202718_137900000.cu8` was evaluated using the installed pipeline in a cloned record and separate SQLite database/event stream. Nominal and shifts -37500/-22500 Hz all exited 0 with zero images. Survey windows include +45000 Hz broad power; this does not establish a satellite carrier. Completed=false, negative_result_verified=false, verification=null. This is an unsuccessful bounded search, not proof of no signal. Original metadata, IQ fingerprint, history, images, and audit records remained unchanged. See `frequency-check.json` and preserved decode logs.

The existing October 5 offset evaluation on `M2-4_20261005_114142_137900000.cu8` also remains unverified (nominal and applied +45000/+60000 Hz; candidate carrier -45000/-60000 Hz). All other uncertain IQ remains retained; it was not reprocessed in bulk because this implementation cannot certify negative results and no deletion is proposed.

## Small regression/reference selection

These named examples form a small documented regression selection. Other files remain for policy/evidence reasons, not as dozens of regression examples. No new pin/metadata edits are needed while indefinite protections apply.

- Zero-output/no-signal candidate: `M2-3_20260929_202718_137900000.cu8`; historical native decoder verification reference and current offset-uncertain example. No verified no-signal capture can honestly be certified by the current negative evaluator.
- Weak/poor-result candidate: `M2-4_20261004_150317_137900000.cu8`; historical SIGNAL/UNUSABLE, retain without claiming a verified poor classification.
- Frequency-offset/uncertain: same September 29 capture (representative positive-offset spectrum windows); existing October 5 evaluation is complementary evidence.
- Historically useful-image capture: `M2-4_20261005_014827_137900000.cu8`; PARTIAL_SUCCESS with three useful products despite SatDump crash, permanently preserve.
- Preserve `M2-3_20261003_221412_137900000.cu8` too: useful products exist despite failed result classification.
- Preserve `V4-VERIFY_20260930_193204_137900000.cu8` and all imported/manual decoder reference records.

Database-associated images (including historical entries): `[('M2-3_20261003_221412_137900000.cu8', [('m23-20261003T191542Z', 21)]), ('M2-4_20261005_014827_137900000.cu8', [('m24-20261005T014957Z', 21)])]`. Images establish evidence to preserve, not an independently re-reviewed quality judgement.

## All raw IQ intentionally retained

Times below are from saved metadata and include the original timezone. Unknown means evidence is absent, not inferred from filename. Database associations and full metadata are in inventory.json.

| Filename | Satellite/pass time | Bytes | Current retention class | Saved decode / useful count | Verified frequency evaluation | Retention reason |
|---|---|---:|---|---|---|---|
| M2-3_20260928_223042_137900000.cu8 | M2-3 / 2026-09-28T22:32:12+03:00 | 398,721,024 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-3_20260929_202718_137900000.cu8 | M2-3 / 2026-09-29T20:28:48+03:00 | 401,342,464 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-3_20260929_220706_137900000.cu8 | M2-3 / 2026-09-29T22:08:36+03:00 | 410,517,504 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-3_20260930_115106_137900000.cu8 | M2-3 / 2026-09-30T11:52:36+03:00 | 417,333,248 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-3_20260930_200427_137900000.cu8 | M2-3 / 2026-09-30T20:05:57+03:00 | 1,548,746,752 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-3_20261001_212022_137900000.cu8 | M2-3 / 2026-10-01T21:21:52+03:00 | 1,675,624,448 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-3_20261002_110436_137900000.cu8 | M2-3 / 2026-10-02T11:06:06+03:00 | 1,646,788,608 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-3_20261002_223753_137900000.cu8 | M2-3 / 2026-10-02T22:39:23+03:00 | 1,571,291,136 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-3_20261003_122125_137900000.cu8 | M2-3 / 2026-10-03T12:22:55+03:00 | 1,640,759,296 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-3_20261003_203413_137900000.cu8 | M2-3 / 2026-10-03T20:35:43+03:00 | 1,622,409,216 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-3_20261003_221412_137900000.cu8 | M2-3 / 2026-10-03T22:15:42+03:00 | 408,682,496 | processing_failed | EMPTY/FAILED / 3 | False | Processing or capture failed; retained indefinitely |
| M2-3_20261004_115807_137900000.cu8 | M2-3 / 2026-10-04T11:59:37+03:00 | 416,284,672 | unverified | EMPTY/FAILED / 0 | False | Historical or incomplete frequency evaluation; retained |
| M2-3_20261005_083451_137900000.cu8 | M2-3 / 2026-10-05T08:36:21.699359+00:00 | 420,216,832 | unverified | EMPTY/FAILED / 0 | False | Historical or incomplete frequency evaluation; retained |
| M2-3_manual_20260928_2112_137900000.cu8 | unknown / unknown | 99,090,432 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-4_20260929_051817_137900000.cu8 | M2-4 / 2026-09-29T05:19:47+03:00 | 420,741,120 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-4_20260929_150958_137900000.cu8 | M2-4 / 2026-09-29T15:11:28+03:00 | 0 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-4_20260930_045637_137900000.cu8 | M2-4 / 2026-09-30T04:58:07+03:00 | 416,808,960 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-4_20260930_144950_137900000.cu8 | M2-4 / 2026-09-30T14:51:20+03:00 | 1,679,294,464 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-4_20261001_043500_137900000.cu8 | M2-4 / 2026-10-01T04:36:30+03:00 | 1,634,467,840 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-4_20261001_142820_137900000.cu8 | M2-4 / 2026-10-01T14:29:50+03:00 | 1,654,915,072 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-4_20261001_160849_137900000.cu8 | M2-4 / 2026-10-01T16:10:19+03:00 | 1,607,729,152 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-4_20261002_041325_137900000.cu8 | M2-4 / 2026-10-02T04:14:55+03:00 | 1,575,223,296 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-4_20261002_140657_137900000.cu8 | M2-4 / 2026-10-02T14:08:27+03:00 | 402,915,328 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-4_20261002_154649_137900000.cu8 | M2-4 / 2026-10-02T15:48:19+03:00 | 1,657,012,224 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-4_20261003_053146_137900000.cu8 | M2-4 / 2026-10-03T05:33:16+03:00 | 1,679,556,608 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-4_20261003_152459_137900000.cu8 | M2-4 / 2026-10-03T15:26:29+03:00 | 1,681,653,760 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |
| M2-4_20261004_065024_137900000.cu8 | M2-4 / 2026-10-04T06:51:54+03:00 | 386,138,112 | unverified | EMPTY/FAILED / 0 | False | Historical or incomplete frequency evaluation; retained |
| M2-4_20261004_150317_137900000.cu8 | M2-4 / 2026-10-04T15:04:47+03:00 | 420,216,832 | unverified | SIGNAL/UNUSABLE / 0 | False | Historical or incomplete frequency evaluation; retained |
| M2-4_20261005_014827_137900000.cu8 | M2-4 / 2026-10-05T01:49:57.513173+00:00 | 1,665,400,832 | processing_failed | PARTIAL_SUCCESS / 3 | False | Processing or capture failed; retained indefinitely |
| M2-4_20261005_114142_137900000.cu8 | M2-4 / 2026-10-05T11:43:12.821852+00:00 | 419,954,688 | processing_failed | EMPTY/FAILED / 0 | False | Processing or capture failed; retained indefinitely |
| V4-VERIFY_20260930_193204_137900000.cu8 | V4-VERIFY / 2026-09-30T19:32:04+00:00 | 59,506,688 | unmanaged/reference; outside cleanup | not established in managed record / 0 | False | Historical unmanaged/reference raw IQ is outside authoritative cleanup |

## Verification

Verified at 2026-10-05T17:08:11.263820+00:00. Immediately after evaluation, original metadata/source hashes and full database contents were exactly unchanged. The ordinary 17:04 UTC retention maintenance subsequently refreshed managed retention checked_at timestamps; final full-history comparison excludes only those timestamps. All other database fields/images, recording JSON, audit records, original source/configuration hashes, raw fingerprints, plan hash, timer unit/activation identities, next planner run and unit enablement remain unchanged. Full timer display text naturally changes as countdowns and recurring services advance. Planner and cleanup service results are success, both timers active. Installed retention unit tests passed; the future cleanup path remains functional in its intentionally gated dry-run mode. No apply was attempted and no validation flag was bypassed. No reboot.

Future disk reclamation requires validated negative evaluation or a supported failed-capture cleanup rule; neither is implemented today. This review intentionally does not modify policy to enable reclamation.
