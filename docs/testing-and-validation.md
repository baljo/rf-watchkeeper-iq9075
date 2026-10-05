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
