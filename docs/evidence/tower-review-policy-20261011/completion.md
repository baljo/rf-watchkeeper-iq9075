# Tower review policy acceptance — 11 October 2026

Implemented, Linux-tested, deployed and production-active on IQ-9075 EVK. Snapshot checks after the dashboard restart passed. Short natural-worker observation passed; reboot and sustained unattended acceptance remain unverified.

## Current-data evidence

At 08:28 UTC / 11:28 Europe/Helsinki: 4,168 capture records, 129 reviewed, 644 unscored. Old queue 447. At 08:31 UTC / 11:31 Helsinki: 4,170 records, 646 unscored; the same scored population yields 77 selected (59 persistent AD, 18 audit). Grey-zone pool 322, audit 18 / 322 = 5.59%, within the requested 5–10% range. Newest-first UI remains capped at 20; first page has 19 persistent and one audit clip. Counts are dated live observations, not fixed expectations. See census.json and live-verification.json.

## Tests and exact procedure

Staged current live Python dependencies and canonical tests under `/tmp/tower-review-test`, with new atis_view/policy. Ran `PYTHONTZPATH=/tmp/tower-review-test/tz python3 -m unittest test_tower_review_policy test_tower_threshold_queue test_tower_scored_queue test_tower_recent test_tower_retention test_tower_failures test_tower_ad_batch test_tower_anomaly_review test_tower_validation test_atis_shadow test_meteor_retention test_dashboard_state_isolation`: **99 tests passed**, 10.679 seconds (tests.txt). Timezone fixture is repository Helsinki.tzif copied into isolated tz/Europe/Helsinki; no production timezone change.

Initial Windows run: six pure policy/threshold tests passed; three Linux-dependent modules could not import fcntl. Initial Linux staging used older live tests (two stale Tower expectations, an ATIS retention fixture error, one missing module, one stale ASR expectation); corrected to canonical test versions. Next run: 98 passed and one staging timezone error; supplied the isolated timezone fixture and all 99 passed. No production behavior changed to accommodate tests.

Pre-deploy live queue HTTP attempt timed out at 15 seconds; an aggregate parsing command also had a quoting error. Census succeeded independently. Immediate request after restart raced dashboard startup and returned connection failure. Later Python HTTP acceptance returned 200 for queue, state, ATIS and METEOR schedule, with all displayed items eligible. No private API bodies/tokens were exported.

## Deployment and rollback

Live atis_view was inspected and matched repository behavior. Backed up original atis_view.py and dashboard.html under `/root/rf-watchkeeper/backups/tower-review-20261011/`. Installed atis_view.py, tower_review_policy.py and three regression tests. Applied only review text substitutions to live HTML with UTF-8 surrogateescape to preserve legacy bytes and private map settings. Initial strict UTF-8 update failed without modifying HTML; corrected byte-preserving update succeeded. Restarted **only rf-watchkeeper-dashboard.service**. No worker/model/retention/capture service restart or RF intervention.

Rollback: restore only original atis_view.py and dashboard.html from that backup and restart dashboard; preserve later labels/pins/recordings. New unused policy module may remain. Retained model threshold unchanged; source SHA-256 identities of tower_anomaly.py, tower_anomaly_shadow.py and tower_retention.py were identical before/after. Exact public source patch retained in changes.patch. Review values/defaults and stable audit salt documented in config/examples/tower-review-policy.md.

## Standing completion rules

1. Live inspection: passed, source/services/current dataset inspected.
2. Exact patch and evidence: passed.
3. Tests/failures: recorded above and passing output retained.
4. Dated shared project log: appended and synchronized.
5. Canonical status/architecture/operations/dashboard/policy/config: updated and synchronized.
6. Rollback: backed up and documented.
7. Maturity: implemented/tested/deployed/active; short automatic observation only.
8. Dashboard restart persistence: verified through live HTTP; reboot unverified, no disruptive reboot performed.
9. Live counts: census.json; labels untouched.
10. Privacy: aggregate-only evidence, no private locations/network identities/credentials/raw audio/model artifacts published; explicit staged-file review.
11. Decisions preserved: Tower ASR deferred, 30-day policy and pins unchanged, METEOR deletion unchanged. Detector/scientific threshold 45.67438250526811 preserved; no retraining.

Hardware/RF actuation acceptance is not applicable to a read-only queue policy. Existing retention enforcement gap, model sensitivity, correlated windows, native DMA/Genie faults and integrated reliability remain open. Missing windows fail closed for routine persistence; inclusive history/reference validation remains available. The 8% hash sample estimates grey-zone miss rate only; it does not cover high-score isolated spikes. Public Git publication is verified separately by the final commit and remote check.
