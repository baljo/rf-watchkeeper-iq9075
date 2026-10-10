# Repository documentation audit completion — 10 October 2026

Scope: canonical RF Watchkeeper repository after Arduino/Qualcomm showcase submission. Baseline `bf0edb702790a06b9f1923ebc6346d2e9001de60`; live snapshots around 06:49–06:55 UTC / 09:49–09:55 Europe/Helsinki. Synced `sources/` were read-only and unchanged.

## Changes and evidence

README/current topic guides now describe live scheduling, architecture, service layout, device1 ATIS/shadow/reference queues, Tower ASR deferral/acoustic screening/completed-AD review filter, AIS reception history, METEOR settings, retention and known failures. Exported already-deployed dependencies and effective unit/drop-in snapshots resolve missing runtime source. Public observer fixtures/map centres remain approximate; precise coordinates/API tokens/raw private snapshots are excluded. Four invalid UTF-8 characters in the installed dashboard are normalized only in the export; no live HTML replacement occurred.

The exact file inventory is [changed-files.json](changed-files.json). Live hashes/configuration/API checks, source-export distinctions and intentionally excluded drift are [inspection.json](inspection.json). The new dated shared log entry preserves historical chronology. Historical log/stage links to private excluded evidence remain explicitly identified as EVK-only; current guide links/source references are validated separately.

## Verification performed

- Existing authorized SSH identity reached the EVK; read source/config/services/drop-ins, retained outputs, pause state, human-label inventory and endpoint-specific API results. No credentials or precise observer values enter public evidence.
- Initial deployed fixture run: 58 tests, 5 failures, 3 errors, 1 skip; 49 passed. Stale old queue/display/preflight contracts, incomplete mocks and absent installed test identified, not hidden. [Exact command/failures](initial-test-results.txt).
- Existing current-contract EVK safety suites: **29 tests passed**, 10.475 s, no skips. Temporary roots/mock processes only, no actual RF/model inference. [Command/output](current-test-results.txt).
- Updated checkout in local Ubuntu: **74 tests passed**, 11.081 s. Covers accelerator lease/queue preservation, Tower retention/pins/review/failures, AIS positions/history and adaptive scheduling/preemption. Four fixture contracts/mock paths refreshed without changing runtime behavior. SQLite ResourceWarnings from existing AIS fixture connections are non-fatal and recorded; no production DB change. [Summary](local-test-results.json).
- Local anomaly suite with disposable NumPy 2.5.3 wheel: **10 passed, 1 skipped** in 0.439 s. The skip requires private `TOWER_ANOMALY_EVIDENCE`; no private manifest accuracy/leakage check claimed. [Output](numpy-tests.txt). Wheel SHA256 `b0521d0f4aebb6e06189451025fa17a913287b13c03d5fe05c017333b654ea5b`; temporary dependency removed when the test context exited.
- Static current-guide link/fence/source-reference checks, all exported Python syntax, known config invariants: [validation.json](validation.json), rerunnable `python docs/evidence/repository-audit-20261010/verify.py`.
- Markdown rendered using bundled marked; inline dashboard scripts syntax-checked without execution: [render-validation.json](render-validation.json), rerunnable `node docs/evidence/repository-audit-20261010/verify.cjs [dependency-directory]`.
- Git diff whitespace, explicit file review, precise-location/token/private-address and generated/large-file checks before commit. Test-output trailing whitespace is normalized without changing commands/results. No proprietary model/binary, live config, raw media/database, private access note or synced reference file staged.

Earlier test staging/archive and in-memory source-transfer proposals were rejected by automatic approval review for source-egress concerns. No rejected transfer was performed. Verification instead used existing EVK fixtures plus the local Ubuntu checkout. Initial local runs exposed missing NumPy and incomplete fixture isolation; these were corrected/retested as above. Real RF/HTP performance, clean install, reboot and extended unattended acceptance were not rerun merely for documentation.

## Standing workflow rules 1–11

1. Live state inspected directly; dated snapshots and endpoint failures retained.
2. Exact exported source/config references and unit snapshots retained in Git; runtime behavior was already deployed. Private live source hashes permit comparison; export privacy/encoding/fixture differences are explicit.
3. Exact tests/results/failures/skips recorded; local source syntax/render/config checks saved.
4. Dated project log/current documentation synchronized to the EVK at 07:17 UTC / 10:17 Helsinki; documentation backup and matching hashes verified, runtime/private-config hashes unchanged. [Synchronization receipt](sync-receipt.json) records the latest documentation-only copy.
5. Current README, architecture, setup, scheduling, services, pipelines, retention, utilization, dashboard and recovery guides reconciled.
6. No runtime rollback needed. Public rollback: revert this scoped commit. Shared-doc rollback: restore only affected documentation from the audit snapshot, preserving newer log entries/data/configuration. Never restore an entire old project over current state.
7. Export implemented/tested; mirrored runtime already deployed/production-active where identified. AD/ASR candidate paths labeled shadow. Completed integrated unattended acceptance remains **FAIL/open**, not relabeled passed by fixture success.
8. No runtime restart/reboot needed or performed. Real watchdog reboot, full cleanup persistence and long-run capacity remain unverified.
9. Counts read live and dated: 111 Tower labels; 31 raw satellite cu8 / 18,356,895,744 bytes; latest 12 retained ATIS outputs partial/failed Genie. No invented references/labels.
10. Public approximate Vaasa/Korsholm wording; private coordinates/session tokens, local access note and private snapshot files excluded. Source/tests/evidence included in review.
11. Tower ASR deferred, 30-day policy/pins preserved, failed/unverified satellite raw not automatically deleted, production/shadow distinctions retained. No deletion/probe/reset/reboot/threshold/scheduling/runtime-setting change.

## Remaining operational limitations

Integrated DMA/native/Genie failures, state/review API timeouts, Tower throughput and incomplete enforcement of the 30-day policy for acoustic-only captures, ATIS accuracy/reference/archive bounds, SatDump SIGSEGV/live-image repeatability, optional SDR interference/physical inventory, external runtime/build acquisition, fresh installation and real reboot acceptance remain open. [Full current disposition and rationale](../../current-status.md). They require separately tested runtime/field work; this audit documents actual behavior without making an unrequested operational change.

Documentation/source reconciliation is distinct from runtime acceptance. The session reports actual shared synchronization, Git commit/publication hashes and any failed gates; a prepared snapshot is not itself proof of publication or synchronization.
