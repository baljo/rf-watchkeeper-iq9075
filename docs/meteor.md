# METEOR current behavior

Verified 2026-10-05. Reuse [METEOR_AUTOMATION.md](legacy/meteor-automation.md) for installation, planning and retention details and [AUTONOMOUS_EVK.md](legacy/autonomous-evk.md) for the pinned EVK SatDump runtime. Those guides describe the October 3 installation snapshot: automation was initially disabled and the recorder default was 1.024 MS/s. Current configuration differs.

## Current operation

`meteor-config.json` enables automation, disables deletion (`cleanup_enabled: false`), and selects V4MAIN01 at 137900000 Hz, gain 49.6 dB, **256000 samples/sec**. Current active and future managed plan entries also use 256000. Historical pass metadata retains its actual recording rate; do not rewrite old 1024000 recordings to match today's configuration.

Planning uses a 36-hour window, 10-degree horizon, minimum peak 25 degrees, at least 60 seconds in azimuth 120–240, and four passes per Helsinki day, respecting manual reservations. Capture margins are 90 seconds with 120-second preflight. Planning, dispatch, processing and cleanup timers are active; cleanup remains gated off by configuration. Persistent pass records and logs are under `data/meteor-auto/`.

EVK SatDump runs `meteor_m2-x_lrpt` on unsigned `cu8` IQ with the recorded sample rate and explicit M2-3/M2-4 selection. Native package/image identity and restrictions remain documented in the existing EVK decoder guide. Decoder availability does not establish useful imagery.

## SIGSEGV with useful retained products

The October 5 fix in `meteor_store.py`, `meteor_pipeline.py`, `test_meteor_history.py` and `dashboard.html` recognizes `PARTIAL_SUCCESS` / `decoded_with_satdump_crash` while preserving the nonzero return code and explicit SIGSEGV diagnostic.

The exception requires a fully validated native channel PNG at least **256×128** and at least **128 matching decoded channel lines**, with no explicit processing error or recognized invalid-pipeline/runtime diagnostic. Return codes 139 and -11 identify SIGSEGV. PNG validation includes complete chunks, CRCs, inflated pixel size and scanline filters. Tiny/corrupt/empty output and error cases remain failures.

Implementation detail: existing line-count accounting uses decoder log lines when available; absent a channel count, it can use the validated native channel PNG height, or explicitly supplied known lines. The current regression pass uses actual decoder-log counts. Do not claim that every accepted pass necessarily has a separate log count.

For `m24-20261005T014957Z`, all three attempts retain `returncode=139` and `satdump_crash=SIGSEGV`. Channel counts are 888/896/888 for channels 1/2/4, peak SNR 7.069854. Capture completed at historical 1024000 samples/sec. Products from the three attempts have identical hashes: retries used the same IQ and settings. Seven current products are indexed and dashboard-readable; all 21 PNGs remain retained.

Automatic processing and worker listing/claiming exclude the completed partial-success state independently of the attempt limit; no fourth automatic retry occurs. Failed decodes remain retryable within the configured three-attempt limit and one-hour delay.

Evidence: [exact source patch](evidence/meteor-satdump-crash.patch), [original 53-test output](evidence/meteor-crash-tests.txt), [retained regression report](evidence/meteor-crash-regression.json), [current API inspection](evidence/documentation-inspection.json), and [engineering log](project-log.md). The original backup and EVK regression stage remain under `backups/meteor-crash-20261005T1055/` and `meteor-crash-stage-20261005/`.

The dashboard reads `data/watchkeeper-meteor.db` through `/api/meteor`, with current-per-product selection and retained attempt history, controlled image routes and schedule display. Imported reference recordings are distinct from automatic EVK passes. Decoded output does not by itself certify reception quality or image interpretation.

## Dry-run retention classification — 2026-10-05

Actual deletion remains disabled by both `cleanup_enabled=false` and `retention.automatic_deletion_validated=false`. No raw IQ was deleted during this correction. The classifier and dry-run candidate list work independently of these two execution gates. `cleanup --apply` still refuses if either gate is false.

The previous implementation excluded most historical IQ because it only visited managed pass records. It also treated every failed/unverified result as indefinite retention and required an exhaustive negative frequency search that no production workflow could certify. Disabled gates were already separate from the old eligibility check; the observed zero candidates primarily came from these inventory/evidence requirements, rather than the gate values themselves.

`meteor_retention.inventory_records()` now includes every `recordings/satellite/*.cu8`, associates managed history, reads historical recording JSON and consults separate review records. Absence of a managed record does not imply reference protection. Historical evaluations live under `data/meteor-auto/retention-review/<raw-stem>/`, with chronological commands, logs, metrics, offset survey, selected output and raw fingerprint. Existing capture metadata and managed attempts are preserved. Additional products and a separate evaluation database remain under the review/staging directories.

| Disposition | Meaning |
|---|---|
| PROTECTED | Explicit Keep/reference/regression material, useful channel products from any historical or current attempt (including crash outputs), or an active capture/decode/search/worker owner |
| GRACE | A recent capture is still inside its finite configured grace period |
| DELETABLE | Grace expired, raw fingerprint/metadata are consistent, and the current supported nominal plus configured frequency-offset procedure completed without a decoding failure and produced no useful/partial channel evidence; an expired zero-sample `failed_no_iq` capture is also eligible and reclaims zero bytes |
| REVIEW | Missing/inconsistent metadata, changed raw IQ, real decoder/capture errors, timeouts, incomplete search, unusual frequency/troubleshooting evidence, or partial/signal evidence needing judgment |

`disposition` is the authoritative policy result; existing lowercase `retention_class` and decoder `classification` remain separate descriptive fields for compatibility. `eligible` and `would_delete` express hypothetical eligibility regardless of execution gates. Summary counts/bytes include existing raw files only; missing raw managed records remain in history without inflating totals. Explicit protections are recorded by exact basename/reason in `data/meteor-auto/retention-protected.json`. Useful MSU-MR channels require width ≥256 and height ≥128 (configured `useful_min_lines`). A later failed selected attempt cannot erase earlier useful-image protection. Imported/manual verification references remain protected.

### Finite grace

The existing configured durations are retained: `no_signal_hours=24`, `poor_hours=48`. Grace now starts at saved capture completion (`actual_stop`, or saved `record_stop`), not the latest re-evaluation. This is a deliberate semantic correction: repeated failed evaluations cannot continually restart grace. No arbitrary duration was added. No-image/uncertain captures use 24 hours; partial/synchronized signal evidence uses 48 hours and becomes REVIEW after grace unless useful products protect it. Missing completion timestamps require REVIEW. `useful_hours=168` and `raw_retention_days=14` remain compatibility fields; useful channel products are protected rather than aged out. Disk pressure never shortens grace or overrides protection.

### Frequency and decoder evidence

Before an old nonempty no-image IQ file can become DELETABLE, run the existing supported native SatDump wrapper using the **recorded** sample rate and satellite. The existing spectrum survey spans ±60 kHz, samples 24 windows, and ranks two candidate carrier offsets. The wrapper's `--freq_shift` applies the opposite sign of each surveyed carrier offset. Trials keep separate output directories. The existing additional search budget remains 300 seconds; historical review nominal attempts use a bounded 180-second timeout without changing production capture/decoder configuration. No assumption requires the carrier to be exactly 137.900 MHz.

`procedure_completed` means the supported bounded procedure completed. It is deliberately separate from `completed`/`negative_result_verified`: sparse surveys and zero images do not establish physical absence of signal or exhaustive offset coverage. Retention is a finite policy decision after this supported procedure, not a claim of scientific proof. Candidate evidence is tied to the raw fingerprint, wrapper/native runtime manifest identity, pipeline options and current search configuration. Missing shifted trials, changed decoder/search configuration, a budget error, crashes, or incomplete processing produce REVIEW. Stronger future searches may recover signals missed by the current procedure; review the candidate list before any cleanup authorization.

The strict original `evaluation_clean` marker is preserved. Retention distinguishes known nonblocking file-decoder notices about four unused optional SDR plugins and unavailable celestrak.org TLE refresh from actual decoder errors. It checks full logs for required `Demodulation finished` and `Done! Goodbye` markers; unknown error lines, invalid arguments, timeouts and crashes remain blocking. Spectrum power alone is never deletion evidence. Partial channel/image evidence or actual synchronized decoder evidence remains REVIEW after grace; a `SIGNAL/UNUSABLE` label caused solely by positive noise SNR with NOSYNC does not establish ambiguity; documented troubleshooting/reference captures remain PROTECTED.

### Persistence and execution safeguards

Dry-run classification does not rewrite capture metadata, pass history, database rows, raw IQ or images. Maintenance may persist retention metadata and review evidence. Hypothetical raw-only deletion retains recording JSON, pass records, chronological attempts, decoded images, evaluation database/history and durable retention audit entries. No cleanup operation deletes images or metadata. Shared capture/processing/retention locks, active-owner exclusions, approved raw directory/suffix, fingerprint checks, exclusive raw advisory locks and open-reader checks remain in place for any future gated execution.

### Exact inventory and verification

The current complete report, JSON and CSV are linked below. They list filenames, saved satellite/pass timestamps, recorded sample rates, exact bytes, MiB/GiB, disposition/reason, image evidence, explicit reference status and age. Group totals distinguish all satellite raw IQ from the METEOR subset and separately quantify >1 GiB, 256 kS/s, 1.024 MS/s, protected/reference and failed/no-image material.

- [Exact dry-run inventory and report](evidence/retention-classifier-report.md)
- [Machine-readable inventory](evidence/retention-classifier-inventory.json)
- [Inventory CSV](evidence/retention-classifier-inventory.csv)
- [Authoritative dry-run output](evidence/retention-classifier-dry-run.json)
- [Verification and live health](evidence/retention-classifier-verification.json)
- [Tests](evidence/retention-classifier-tests.txt)

The test suite covers disabled deletion gates with nonzero dry-run candidates, useful/crash/historical product protection, recent failed grace, old no-image eligibility, actual errors and ambiguous signal REVIEW, explicit references, old 1.024 MS/s no-image material, hypothetical metadata/history/image persistence, changed fingerprints, missing trials, changed decoder/search identities, scope checks, locks, open readers and unchanged conservative duration minima. The metadata-survival test simulates deletion metadata without deleting its raw test file. The capture/recovery suite uses mocked reboot/device operations; no real reboot or hardware recovery was invoked.

Older managed records that predate fingerprint collection can be evaluated in a separate review record after confirming the current raw matches the task baseline and recorded capture size. The review records explicitly describe this new fingerprint provenance; they do not invent a capture-time fingerprint or rewrite original metadata.


Verified result: PROTECTED: 9 files / 7,986,741,248 bytes; GRACE: 2 files / 840,171,520 bytes; DELETABLE: 18 files / 19,179,241,472 bytes; REVIEW: 2 files / 2,033,188,864 bytes. Dry-run reclaimable 19,179,241,472 bytes; actual reclaimed 0. 84 staged/deployed tests passed. Both deletion gates remain disabled.

### Approved cleanup completed — 2026-10-05

Following explicit user approval, only the reviewed 18 DELETABLE raw files were deleted: 19,179,241,472 bytes (17.862060546875 GiB). The 13 remaining satellite raw files total 10,860,101,632 bytes; protected/grace/review material, all recording JSON, products, decoder attempts and database history remain intact. Planner, timers and RF services are healthy. Both persisted automatic-deletion gates remain false. The deletion audit now records supported-procedure completion separately from exhaustive negative verification; no false negative-signal certification is implied. See [authorized cleanup report](evidence/retention-approved-cleanup-report.md) and [verification](evidence/retention-approved-cleanup-verification.json).

## Current frequency handling and publication inspection

Production `decode()` calls `decode_once()` for the nominal decode, then `evaluate_frequency()`. A nominal nonzero exit/error stops offset evaluation and retains normal bounded retry behavior; useful crash products are not redundantly searched. For a clean nominal result without useful channels, the recorded-rate spectrum survey ranks at most two offsets, and `decode_once(..., frequency_shift=-carrier)` passes `--freq_shift` through `satdump_evk.py` into native SatDump. Separate outputs/attempts retain each trial and selection. Useful nominal output does not require an additional shifted search.

This is explicit external candidate correction, not verified exhaustive native acquisition coverage. No numeric claim about SatDump's internal carrier-loop capture range was established. Tuning to 137.900 MHz does not prove centered LRPT; sparse survey/interference/weak-signal limitations remain. Historical recordings retain their original rate and frequency.

Later read-only [publication inspection](evidence/publication-inspection.json) found 14 raw satellite cu8 files totaling 11,281,367,040 bytes, reflecting capture after the earlier cleanup snapshot. No raw file, product, historical metadata, retention gate or satellite schedule was modified for documentation. Indoor imagery remains experimental: useful channel products demonstrate that weak indoor captures can be recoverable, not reliable pass-by-pass reception.

## Live reconciliation — 10 October 2026

The live configuration still enables automation at 256000 samples/s, 137900000 Hz and gain 49.6 dB on V4MAIN01. Planning remains 36 h, 10-degree horizon, minimum 25-degree peak, south sector 120–240 degrees for 60 s, maximum four passes/day. Margins are 90 s before/after with 120 s preflight, 12 s dispatch lead and 30 s maximum lateness. TLE maximum age is 3 days. Free-space gate requires 10 GiB beyond estimated capture storage. Decode timeout is 1800 s, at most three attempts with 3600 s retry spacing. Both automatic raw-deletion gates are false.

Plan/dispatch/process/cleanup/legacy-register timers are active; idle successful oneshots are expected. Current raw satellite inventory was 31 cu8 / 18,356,895,744 bytes, a time-dependent snapshot rather than a fixed expected count. Useful retained partial-success products do not resolve SatDump SIGSEGV or establish reliable live pass reception. [Audit evidence](evidence/repository-audit-20261010/inspection.json).
