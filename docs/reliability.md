# Reliability and recovery

The detailed implementation guide is [RF_HEALTH.md](../RF_HEALTH.md); preserve and update that guide rather than duplicating its design here. [Project log](project-log.md) records dated implementation evidence and limits.

Current installed components include `rf_health.py`, `rf_health_monitor.py`, sample-reporting integrations, `rf-health-config.json`, health service/timer and dashboard health display. V4MAIN01 is enabled/required; 43300001 is disabled. Health uses sample evidence independently of application output. Its SQLite tables exist alongside existing application tables.

At 11:38:58 UTC on 2026-10-05, the health journal reports successful completion; `Result=success` and `ExecMainStatus=0` were observed. An earlier 11:28:08 UTC entry records a successful prepass check for `m24-20261005T114312Z`. The five-minute timer is active. These are verified installed behaviors; ongoing work elsewhere and these observations do not establish final acceptance or long-term unattended reliability.

V4 capture/recovery source and October 4 backup show bounded IQ preflight, persisted per-pass reboot reservation and post-boot resume paths in `satellite_capture.py`, `meteor_recovery.py` and `satellite_v4_preflight.sh`. Current preflight delegates to the shared sample monitor; managed reboot-only invocation validates a persisted reservation. Existing October 3 installation text saying there is no reboot path applies to that earlier addition, not the entire current recovery implementation.

Current recovery guards protect satellite ownership, restrict automatic reboot frequency through durable shared SQLite state and leave `usb_recovery_command` unset because no receiver-only USB reset facility is verified. No probe, recovery command, reboot, service restart or runtime change was performed for documentation.

Limits: a real reboot test for the new watchdog is explicitly unperformed in the guide; scheduler restoration after the active October 5 capture was not yet observed at this inspection. The scheduler had an exit-code failure label after intentional AIS cancellation for that capture. The second SDR remains disabled/disconnected, with interference cause and remedy unverified. See [hardware](hardware.md) and [experiments](experiments.md).

## Later verified observations — 5 October 2026

The retained 18:46 UTC Airband deployment report observed METEOR-driven scheduler restoration at 18:41:08 UTC after capture. The scheduler/dashboard/Airband worker/health timer were active during the later [publication inspection](evidence/publication-inspection.json). These later observations supersede the earlier inspection's unresolved restoration observation, while the historical text above remains intact. A real new-watchdog reboot acceptance test and long-run reliability remain unverified. See [watchdog and recovery](watchdog-and-recovery.md).

## Current operational limits — 10 October 2026

Health timer and primary services remain active; no new fault injection, forced recovery, USB/DSP reset or reboot was performed. Sample progress still does not imply successful interpretation. Corrected ATIS workers are deployed on device1, but retained DMA growth, Genie failures and dashboard timeouts failed integrated acceptance. Do not reset DSP mappings or restart unrelated services as an undocumented workaround; preserve evidence and protect imminent/active satellite ownership. [Failure details](evk-utilization-status-20261009.md), [current services](operation.md).

Recovery after individual METEOR captures has dated successful observations; full watchdog reboot/end-to-end resume and sustained all-workload reliability remain unverified. Repair/retry Tower failures individually using preserved failure records; never bulk-clear terminal JSON or delete failed/unverified satellite raw IQ. [Tower recovery](tower-failure-fix-20261009.md), [retention](data-retention.md).
