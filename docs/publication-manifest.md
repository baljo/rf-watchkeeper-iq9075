# Initial public publication manifest

Canonical repository: [baljo/rf-watchkeeper-iq9075](https://github.com/baljo/rf-watchkeeper-iq9075). Remote inspection found no refs/commits; this is an initial import, not a rewrite of remote history. EVK remains the deployed source at `/root/rf-watchkeeper`, without Git installed/metadata at inspection.

Original implementation/doc snapshot: `/root/rf-watchkeeper-doc-snapshots/20261005/source-before.tar.gz`. Existing chronological log entries were preserved verbatim and a publication entry appended. Historical Markdown links into `data/` and `backups/` in that log refer to EVK-only evidence; these runtime paths are intentionally excluded from Git. Original snapshots retain their exact document bodies.

## Intentionally excluded

All satellite raw IQ and decoded runtime images, WAV/audio archives, databases/WAL files, runtime event/log streams, frozen raw Hydro input, backups/staging, models/native binaries/containers, live decoder manifest/TLE state, access credentials/session tokens/private keys and accidental machine output. No excluded operational file was deleted. Small reports, tests, configs and patches are curated below; no media rights or redistribution license is inferred.

The unused 10 MB full-world map source `static/map/ne_10m_land.geojson` is also excluded; the dashboard uses the small regional `kvarken_land.geojson`, which is included.

## Exported files

The following exact paths are the public initial import. Topic files updated from existing EVK documents are listed separately in the final report; Git marks every file added because remote history was empty.

- `.gitignore`
- `ATIS_POC.md`
- `AUDIO_WORKFLOW.md`
- `AUTONOMOUS_EVK.md`
- `Helsinki.tzif`
- `METEOR_AUTOMATION.md`
- `README.md`
- `RF_HEALTH.md`
- `airband_text.py`
- `ais-config.json`
- `ais_collector.py`
- `ais_display.py`
- `ais_store.py`
- `asr_evidence.py`
- `asr_offline.py`
- `atis_pipeline.py`
- `atis_view.py`
- `audio_tap.py`
- `audio_workflow.py`
- `aviation_benchmark.py`
- `backends/sdr_demo/scheduler.py`
- `dashboard.py`
- `deploy/systemd/meteor-auto-capture.service`
- `deploy/systemd/rf-watchkeeper-atis-process.service`
- `deploy/systemd/rf-watchkeeper-dashboard.service`
- `deploy/systemd/rf-watchkeeper-health.service`
- `deploy/systemd/rf-watchkeeper-health.timer`
- `deploy/systemd/rf-watchkeeper-meteor-cleanup.service`
- `deploy/systemd/rf-watchkeeper-meteor-cleanup.timer`
- `deploy/systemd/rf-watchkeeper-meteor-cleanup.timer.d/retention.conf`
- `deploy/systemd/rf-watchkeeper-meteor-dispatch.service`
- `deploy/systemd/rf-watchkeeper-meteor-dispatch.timer`
- `deploy/systemd/rf-watchkeeper-meteor-legacy-register.service`
- `deploy/systemd/rf-watchkeeper-meteor-legacy-register.timer`
- `deploy/systemd/rf-watchkeeper-meteor-plan.service`
- `deploy/systemd/rf-watchkeeper-meteor-plan.timer`
- `deploy/systemd/rf-watchkeeper-meteor-process.service`
- `deploy/systemd/rf-watchkeeper-meteor-process.timer`
- `deploy/systemd/rf-watchkeeper-meteor-recover.service`
- `deploy/systemd/rf-watchkeeper-scheduler.service`
- `deploy/systemd/satellite-v4-preflight.service`
- `docs/433mhz.md`
- `docs/airband.md`
- `docs/ais-hydro-cadence.md`
- `docs/ais.md`
- `docs/architecture.md`
- `docs/atis.md`
- `docs/dashboard.md`
- `docs/data-retention.md`
- `docs/evidence/airband-ops-20261005/airband-ops.patch`
- `docs/evidence/airband-ops-20261005/install.json`
- `docs/evidence/airband-ops-20261005/report.md`
- `docs/evidence/airband-ops-20261005/test_airband_ops.py`
- `docs/evidence/airband-ops-20261005/tests.txt`
- `docs/evidence/airband-ops-20261005/verification.json`
- `docs/evidence/airband-text-20261005/airband-text.patch`
- `docs/evidence/airband-text-20261005/before.json`
- `docs/evidence/airband-text-20261005/completion-report.md`
- `docs/evidence/airband-text-20261005/install.json`
- `docs/evidence/airband-text-20261005/install_airband.py`
- `docs/evidence/airband-text-20261005/replay-model-initial-path-error.json`
- `docs/evidence/airband-text-20261005/replay-model-result.json`
- `docs/evidence/airband-text-20261005/replay-segmentation.json`
- `docs/evidence/airband-text-20261005/replay_airband.py`
- `docs/evidence/airband-text-20261005/test_airband_text.py`
- `docs/evidence/airband-text-20261005/test_atis_pipeline.py`
- `docs/evidence/airband-text-20261005/tests.txt`
- `docs/evidence/airband-text-20261005/verification.json`
- `docs/evidence/airband-text-20261005/verify_airband.py`
- `docs/evidence/documentation-inspection.json`
- `docs/evidence/documentation-validation.json`
- `docs/evidence/hydro-cadence-20261005/analyze_hydro.py`
- `docs/evidence/hydro-cadence-20261005/audit_payload.py`
- `docs/evidence/hydro-cadence-20261005/hydro-cadence-report.md`
- `docs/evidence/hydro-cadence-20261005/hydro-cadence-results.json`
- `docs/evidence/hydro-cadence-20261005/hydro-database-inspection.json`
- `docs/evidence/hydro-cadence-20261005/hydro-payload-audit.json`
- `docs/evidence/hydro-cadence-20261005/inspect_database.py`
- `docs/evidence/meteor-crash-regression.json`
- `docs/evidence/meteor-crash-tests.txt`
- `docs/evidence/meteor-historical-cleanup-20261005.md`
- `docs/evidence/meteor-retention.patch`
- `docs/evidence/meteor-satdump-crash.patch`
- `docs/evidence/publication-inspection.json`
- `docs/evidence/retention-approved-cleanup-report.md`
- `docs/evidence/retention-approved-cleanup-verification.json`
- `docs/evidence/retention-classifier-dry-run.json`
- `docs/evidence/retention-classifier-inventory.csv`
- `docs/evidence/retention-classifier-inventory.json`
- `docs/evidence/retention-classifier-report.md`
- `docs/evidence/retention-classifier-tests.txt`
- `docs/evidence/retention-classifier-verification.json`
- `docs/evidence/retention-classifier.patch`
- `docs/evidence/retention-documentation-validation.json`
- `docs/evidence/retention-dry-run.json`
- `docs/evidence/retention-frequency-validation.json`
- `docs/evidence/retention-tests.txt`
- `docs/evidence/retention-verification.json`
- `docs/experiments.md`
- `docs/hardware.md`
- `docs/installation.md`
- `docs/meteor.md`
- `docs/operation.md`
- `docs/project-history.md`
- `docs/project-log.md`
- `docs/reliability.md`
- `docs/rf-jobs.md`
- `docs/testing-and-validation.md`
- `docs/troubleshooting.md`
- `docs/watchdog-and-recovery.md`
- `docs/workflow.md`
- `import_satellite_pass.py`
- `interpret.py`
- `interpret_stream.py`
- `job_manager.py`
- `jobs-sensors.jsonc`
- `jobs-v4.jsonc`
- `jobs.jsonc`
- `meteor-config.json`
- `meteor_frequency.py`
- `meteor_pipeline.py`
- `meteor_recovery.py`
- `meteor_retention.py`
- `meteor_store.py`
- `pass_conditions.py`
- `prepare_asr.py`
- `probe_audio_dsp.py`
- `probe_audioreach_api.py`
- `probe_genie.py`
- `profile_encoder.py`
- `recorded.py`
- `register_legacy_meteor.py`
- `rf-health-config.json`
- `rf-watchkeeper-dashboard.service`
- `rf-watchkeeper-health.service`
- `rf-watchkeeper-health.timer`
- `rf-watchkeeper-scheduler.service`
- `rf-watchkeeper.service`
- `rf_health.py`
- `rf_health_monitor.py`
- `rf_sample_relay.py`
- `rf_store.py`
- `satdump_evk.py`
- `satellite_capture.py`
- `satellite_pass.py`
- `satellite_planner.py`
- `satellite_schedule.py`
- `show_events.py`
- `static/map/kvarken_land.geojson`
- `test_ais_validation.py`
- `test_meteor_history.py`
- `test_meteor_recovery.py`
- `test_meteor_retention.py`
- `test_rf_health.py`
- `test_satellite_import.py`
- `watchkeeper.py`
- `docs/publication-manifest.md`
- `docs/evidence/publication-validation.json`

Additional preserved runtime dependencies: `dashboard.html`, `satellite_v4_preflight.sh`, `run_ais_gain_test.sh`.
