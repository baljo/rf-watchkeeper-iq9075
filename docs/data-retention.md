# Data retention and repository hygiene

## Satellite IQ policy

Latest detailed policy: [METEOR](meteor.md), `meteor_retention.py`, `meteor_frequency.py`. Both permanent gates remain **false**: `cleanup_enabled` and `retention.automatic_deletion_validated`. Active maintenance does not mean deletion is enabled.

| Disposition | Meaning |
| --- | --- |
| PROTECTED | Keep/reference/regression captures, useful products from any attempt including crash outputs, active owners |
| GRACE | Finite 24 h no-image/uncertain or 48 h partial/synchronized-signal grace |
| DELETABLE | Grace expired; consistent metadata/fingerprint; supported nominal plus shifted procedure cleanly completed without useful/partial evidence; or expired zero-IQ failure |
| REVIEW | Missing/inconsistent evidence, errors/crashes/timeouts, incomplete search, changed configuration/IQ, unresolved signal/troubleshooting evidence |

Grace starts at saved capture completion, not re-evaluation. Useful/reference IQ is protected rather than expired by compatibility fields `useful_hours=168`/`raw_retention_days=14`. Disk pressure cannot shorten grace or override protections; later failure cannot erase earlier useful images.

Inventory includes historical cu8, not just managed records. The bounded ±60 kHz/24-window/two-candidate search is supported-procedure evidence, not exhaustive proof of no signal. Future gated deletion is raw-only: recording JSON, images, attempts, databases/history and durable audits survive. Shared locks, active-owner exclusions, directory/suffix scope, fingerprints, advisory raw locks and open-reader checks protect execution.

## Historical cleanup and current totals

Earlier inventory: 31 raw files / 30,039,343,104 bytes. A **separately authorized** cleanup removed 18 reviewed DELETABLE files / 19,179,241,472 bytes (17.862 GiB), leaving 13 / 10,860,101,632 bytes at that time. Metadata/images/history remained. [Exact report](evidence/retention-approved-cleanup-report.md), [verification](evidence/retention-approved-cleanup-verification.json).

The 5 October publication inspection found **14 satellite cu8 / 11,281,367,040 bytes**. Normal capture changes totals; historical inventory is a dated snapshot. This task deleted or reclassified no recordings.

## Audio and public Git

Tower originals use `tower_retention.py`: 30 days for completed live Tower audio, permanent pins/Keep/reference trees protected, metadata retained. The legacy latest-20 silent-audio deletion rule is superseded. Newly classified Tower records can lack historical `processed.json`; cleanup requires that file, so a guaranteed all-capture 30-day bound is not established. ATIS finalized no-activity audio can be removed only after shadow/validation holds clear; temporary clips are removed after finalization. Positive ATIS audio and database growth still lack a verified bounded archive policy.

Git excludes raw IQ/WAV, databases, model/native runtime assets, generated runs, backups/staging, raw logs/events, credentials/private keys and machine-specific outputs. Small reports/test evidence and safe source/config snapshots are selected explicitly. See [.gitignore](../.gitignore) and [publication manifest](publication-manifest.md).


## Tower capture visibility — 2026-10-06

Tower displays the latest 20 capture attempts, including no_activity, at the top of Airband. Times use Europe/Helsinki. Available audio has playback/download controls; expired audio retains capture metadata. The latest 20 is a display limit. Current Tower audio retention is 30 days with permanent pins protected; older already-missing audio remains missing. This supersedes the October 6 silent-audio rolling window. See [project log](project-log.md).

## Reconciled live policy — 10 October 2026

Live raw satellite inventory: **31 cu8 files / 18,356,895,744 bytes** at the audit snapshot; normal acquisition makes counts time-dependent. Both automatic deletion gates remain false. Failed/unverified raws are not automatically deleted. The 5 October approved cleanup was a separate one-time action, not authorization for this audit or ongoing deletion.

Tower cleanup accepts only live timestamped `recordings/tower` folders with completed `processed.json`, older than 30 days, without symlink/reference/pin protections; only raw/listening WAVs expire and a separate policy audit is written. New acoustic-only classification uses separate metadata, so the legacy completed-file prerequisite can leave some audio beyond the nominal period. This is documented drift in enforcement, not silently changed production behavior. Permanent pins protect the source and copy originals into `asr-reference-corpus/TOWER-PIN-<id>`; they do not recreate missing audio.

ATIS shadow holds are bounded to 48 h for unfinished eligible queue items; human-validation holds use `atis-validation-hold.json`. These are separate from permanent references. No new global ATIS/database pruning policy is established. This task performed no cleanup, pinning or reclassification.
