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

Read-only inspection during this task subsequently found **14 satellite cu8 / 11,281,367,040 bytes**. Normal capture changes totals; historical inventory is a dated snapshot. This task deleted or reclassified no recordings.

## Audio and public Git

Finalized new Tower/ATIS `no_activity` removes raw/listening WAVs but retains capture/segmentation/transcript/status metadata. Temporary clip WAV/JSON/logs are removed after finalization. Positive/uncertain audio and historical evidence remain. Positive archives and database growth still need a verified bounded policy.

Git excludes raw IQ/WAV, databases, model/native runtime assets, generated runs, backups/staging, raw logs/events, credentials/private keys and machine-specific outputs. Small reports/test evidence and safe source/config snapshots are selected explicitly. See [.gitignore](../.gitignore) and [publication manifest](publication-manifest.md).


## Tower capture visibility — 2026-10-06

Tower displays the latest 20 capture attempts, including no_activity, at the top of Airband. Times use Europe/Helsinki. Available audio has playback/download controls; expired audio retains capture metadata. Silent live Tower WAVs remain within the latest 20 capture folders; older processed silence is pruned without touching speech, reference, ATIS or satellite material. See [project log](project-log.md).
