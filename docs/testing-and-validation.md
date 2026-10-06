# Testing and validation

These are **dated retained results**, not a combined total or a claim that historical suites were all rerun here. Test sets overlap.

| Evidence | Result | Limit |
| --- | --- | --- |
| [Airband operations tests](evidence/airband-ops-20261005/tests.txt), [report](evidence/airband-ops-20261005/report.md) | 28 native EVK tests after current Tower/cadence deployment | Positive live Tower utterance/labelled accuracy unverified |
| [Earlier Airband tests](evidence/airband-text-20261005/tests.txt) | 22 tests; saved native replay | Superseded scheduling; no labelled accuracy |
| [METEOR crash tests](evidence/meteor-crash-tests.txt), [regression](evidence/meteor-crash-regression.json) | 53 tests; preserved useful products/no redundant retries | SIGSEGV remains unresolved |
| [Earlier retention tests](evidence/retention-tests.txt) | Retained output reports 67 tests | Earlier intermediate 25 is not current retained output |
| [Latest classifier tests](evidence/retention-classifier-tests.txt) | 84 staged/deployed tests | Mocked recovery; no actual hardware reboot/reset |
| [Authorized cleanup](evidence/retention-approved-cleanup-verification.json) | Exact reviewed deletion; preservation and gates checked | Separate earlier task |

Retained live deployment examples: two quiet Tower captures **29.184 s**, spacing **185.706 s**, ATIS **89.088 s**, APIs HTTP 200 and satellite-driven scheduler restoration. Quiet capture verifies no-activity handling, not recognition.

Read-only probes during this task returned 200 for state/Tower/ATIS/audio/METEOR/schedule. Dashboard, ordinary scheduler, processing worker and health timer were active; automatic capture inactive at inspection. Status is momentary, not an uptime guarantee. [Inspection](evidence/publication-inspection.json).

Publication validation checks topic/link coverage, EVK-only historical references, prohibited file types, sizes, source hashes and potential secrets before staging. It does not substitute for RF/inference acceptance.

Remaining acceptance: human-labelled speech/numeric accuracy, Finnish recognition, QNN profiling, repeatable indoor METEOR quality, SatDump crash diagnosis, hardware/interference inventory, guarded real reboot/long-run monitoring and clean-device deployment. This task introduced no RF test or operational recovery.

## Watchdog stage classification — 5 October 2026

Tests below predate this audit. The [original watchdog report](evidence/rf-health-original-report.md) retains the 58-test result (11 watchdog, 5 AIS, 42 METEOR recovery/history); these overlapping suites are not summed with later retention tests. [Original live verification](evidence/rf-health-original-verification.json) is timestamped 11:56:04 UTC. The current watchdog source has 11 `HealthTests` cases.

| Stage | Classification | Concrete evidence and limits |
| --- | --- | --- |
| Stale/missing RF success, sample evidence independent of decoded traffic | Implemented and directly tested; also observed in production | `test_quiet_application_and_no_samples`, `test_quiet_ais_with_partial_line_is_bounded`, `test_pending_report_cannot_overwrite_success`; persisted heartbeat_stale at 11:24:21 UTC followed by successful direct probe |
| AIS/Tower/ATIS/METEOR reporting; disabled 433 | Implemented and directly tested / observed in production | Quiet AIS test asserts GREEN and second receiver DISABLED. Original report records all workload sample successes; live SQL shows successful AIS, Tower, ATIS, METEOR IQ preflight and capture, independent of recognition/image output |
| Serial/USB-FD owner identification; bounded owner termination | Implemented and directly tested using controlled processes/mocks | `test_stale_owner_cleanup_controlled_process`, `test_unknown_owner_is_protected`; METEOR `test_cleanup_targets_only_detected_v4_owners`, `test_cleanup_escalates_only_when_v4_owner_remains`. A genuine hardware wedge cleared by this stage is not demonstrated |
| Direct IQ readiness / METEOR prepass | Implemented and directly tested; observed in production | Original 512000-byte probe; current durable events at 11:28:08 and 18:14:03 UTC report 512000 varied bytes and successful prepass. Failure exhaustion covered by mocked `test_failed_stages_respect_reboot_rate_limit` and METEOR `test_real_iq_preflight_rejects_zero_bytes_three_times` (fake recorder, not real SDR) |
| Scheduler restart/reprobe and interrupted-check restoration | Implemented and directly tested with mocked service commands; restoration observed in production | `test_failed_stages_respect_reboot_rate_limit`, `test_restore_after_interrupted_health_service`, `test_scheduler_hard_timeout_cleans_process_group`, `test_intentional_scheduler_stop_exits_cleanly`. Original successful post-capture FM at 11:55:59 UTC; later satellite-driven restoration 18:41:08 UTC. Real escalation curing a hardware failure is not established |
| SDR/USB reset | Not implemented as an operational reset | Optional hook exists but `usb_recovery_command=null`; no verified receiver-only reset. Stage is skipped, not validated or claimed successful |
| METEOR ownership/pass safeguards | Implemented and directly tested; indirectly observed in production | `test_active_satellite_no_probe_or_service_action`; original report BUSY/no recovery while IQ grew 32243712 to 93847552 bytes; 18:25–18:41 UTC satellite handover/restoration. No deliberate collision induced |
| Durable health, API/dashboard | Implemented and directly tested / observed in production | Temporary SQLite tests and `test_hourly_guard_survives_reopen`; original browser report, current `/api/state` GREEN/DISABLED and successful workload APIs. No fresh browser run claimed |
| General watchdog last-resort reboot | Implemented but real recovery not validated | Source reaches `systemctl reboot` only after four failed probes, safeguards and durable guard. Existing test covers rate-limited suppression; no actual watchdog reboot event found, shared guard empty |
| Managed METEOR persisted reboot/resume | Implemented and directly tested by simulation; real end-to-end reboot recovery unclear/unvalidated | `test_persistence_precedes_reboot`, `test_resume_success_keeps_original_argv`, `test_resume_timeout_is_terminal`, `test_current_boot_does_not_duplicate_capture`; retained 84-test output includes simulated post-reboot success/failures. Current recovery records reserved, reboot_count=0; available journal retains one boot only. A boot change by itself does not prove recovery |
| Hourly and per-pass loop protection | Implemented and directly tested | `test_hourly_guard_survives_reopen`, `test_failed_stages_respect_reboot_rate_limit`, `test_one_reboot_only`, `test_concurrent_reboot_request_is_refused`, `test_second_interruption_never_recaptures`; no destructive loop test needed |

**New watchdog/recovery tests in this audit: none.** Five existing AIS validation tests were run offline after changing the observer fixture to an example; all passed. Existing safe-stage validation is adequate; no live fault injection, forced sample probe, receiver reset, scheduler restart or reboot was performed. New work was read-only evidence collection and publication/privacy validation. Genuine remaining gaps are a safe receiver-only USB reset implementation, real fault escalation/hardware recovery and real reboot/resume acceptance, plus long-run monitoring. Do not deliberately cause a risky failure just to close reboot documentation.

## Adaptive hopping — 6 October 2026

48 native scheduler/Airband tests and 111 existing health/AIS/METEOR regression tests passed. Live roughly one-minute Tower probes, AIS gaps, normal ATIS, unchanged Tower recent history/silent audio, and bounded ownership observation passed. METEOR exclusion/preemption and activity extensions used injected capture-loop tests; no positive live Tower transmission or real satellite interruption was induced. See the [report and evidence](evidence/adaptive-rf-20261006/report.md).
