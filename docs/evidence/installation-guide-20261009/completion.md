# Installation guide completion check — 9 October 2026

Scope: documentation only; baseline canonical main `abfe6cf`. No source, runtime config, units, recordings, databases or historical engineering entries changed. Synced project reference files were not modified.

## Verification and evidence

- Read root AGENTS.md and docs/workflow.md before edits; inspected installation, README, operations, hardware, privacy, Airband/AIS/METEOR, source imports/CLI, examples, service snapshots and historical guides.
- Required live read-only inspection attempted through SSH with BatchMode and eight-second connect timeout. Sandbox connection failed; approved network retry reached the EVK but returned authentication failure. No credentials were available. No live state/counts/deployment claimed; private endpoint omitted from public evidence.
- Run `node docs/evidence/installation-guide-20261009/verify.cjs` from checkout (optional argument: dependency directory containing marked/playwright): renders with bundled marked/headless Edge (Chromium), checks all relative links in installation/README and the new log entry, code fences, table/code rendering, page overflow and added-prose coordinate-pair pattern. Results in validation.json. Preview HTML/PNG remain outside Git; full-page screenshot visually inspected for heading separation, code blocks and expected-results table.
- Initial rendering attempts failed because bundled Playwright Chromium was absent and sandbox Edge launch failed; using installed headless Edge with approved execution resolved this. Initial whole-log link scan found three historical links into intentionally excluded runtime data/backups; they were left intact and checks scoped to the new entry. Generated validation.json is checked after generation by final path inspection.
- Run `git diff --check`; explicitly review selected diff, staged paths, private-location/secrets and sizes before commit. Only documentation, checker and sanitized completion/results are in scope. No precise observer coordinate, credential, private device address or model artifact added.
- Runtime tests skipped: no executable application changes; no fresh ARM64 device or authenticated live EVK access. Existing historical tests are not claimed rerun.

## Standing workflow rules 1–11

1. Live inspection attempted, **unmet** due to authentication; repository/dated evidence only.
2. Exact documentation change retained in Git; no production code/config patch applicable.
3. Exact checker and results saved; SSH failure and runtime-test skips explicit.
4. Dated canonical shared project-log entry added; **live EVK mirror update pending** access.
5. Installation and README updated; behavior/architecture/operations unchanged, so no competing current-status rewrite.
6. Rollback: revert only the documentation commit; no runtime rollback needed.
7. Implemented/documentation-validated only; not deployed, production-active or unattended-verified by this session.
8. Restart/reboot checks not performed; prose changes need no restart. Existing operational persistence limitations remain open.
9. No current counts/statistics claimed; dated observations remain dated.
10. Added text/evidence reviewed for location privacy; private local configs remain excluded.
11. Tower ASR deferral, 30-day audio/pins and failed/unverified satellite raw preservation retained; no production/shadow changes.

## Publication and completion limits

Commit and normal non-force push of explicit documentation paths are required by workflow; the session reports their result. Fresh-install acceptance and external dependency acquisition remain outstanding. The documentation repair can be reviewed independently, but overall live-inspection/shared-EVK completion gates cannot be marked passed.
