# ADS-B map and light theme completion — 1 November 2026

Implemented, tested, deployed and production-active. Unattended session completion
and full EVK reboot are unverified. Dashboard-only restart persistence passed.

## Tests and browser verification

Commands on EVK, from `/root/rf-watchkeeper`:

```
python3 -m unittest -v test_adsb_positions test_dashboard_state_isolation test_validation_capacity test_rf_health test_ais_validation test_acquisition_control
python3 -m unittest discover -s adsb-session -v
python3 -m unittest -v test_adsb_positions
```

29 + 7 = 36 tests passed; the final six position tests passed again after the
same-session callsign fallback. AIS script assertions also passed at import.
Existing RF-health tests emitted ResourceWarning about unclosed fixture SQLite
connections; there were no test failures/skips. Exact private transcripts remain
in `adsb-session/private/map-light-deployment-20261101/tests.txt` and
`positions-final-tests.txt`. Synthetic RF-failure messages in these logs belong
to tests, not live capture failures.

Browser checked 1280x1000 desktop and 390x844 mobile: fixed light body/cards/map
controls, actual historical markers, fit, popup, OSM background/attribution,
12-second live refresh and zero horizontal page overflow on mobile. Computed
body background rgb(244,247,250), text rgb(20,34,53), color-scheme light. Screenshot
proof retained locally outside the public repository to avoid publishing raw
positions. Browser displayed zero fresh and two historical positions. Fresh
markers are covered by fixtures; no fresh report existed for a live screenshot.
Empty-default and unavailable-feed behavior were observed; cached positions
expire/demote automatically. Map popups show missing decoder fields as unavailable.

The linked dashboard loaded with its light theme and existing navigation.
Private DB/state/log routes returned 404; arbitrary position parameters returned
400. Five cached endpoint requests took 0.009 seconds. See verification.json.

## Completion gate audit

1. Actual EVK source/schema/service/state inspected before changes: passed.
2. Exact source changes preserved in this Git commit and private originals: passed.
3. Tests/commands/results, warnings and operational limits recorded: passed.
4. Dated project-log appended: passed.
5. Current status, architecture, dashboard and operation docs updated: passed.
6. UI-only rollback recorded in docs/adsb-session.md: passed.
7. Implemented/tested/deployed/active distinguished from unattended verification: passed.
8. Dashboard restart passed; full reboot explicitly unverified to preserve capture.
9. Actual dated live counts recorded, no inferred fresh detections: passed.
10. No receiver coordinates/credentials/private runtime data published: reviewed.
11. Existing RF, retention and deferred ASR decisions preserved: passed.

No capture, decoder, monitor or watchdog restart; only isolated dashboard restarts.
Identity compared against the prior dashboard deployment record: same PID/start
 ticks, container ID/start time, three attempts and expiry. Watchdog activation
was unchanged across initial deployment and remains active. RF units stayed
paused under the existing lease. Expiry: 2 November 09:00:45 Helsinki.

No track replay implemented. Historical markers are bounded last-known reports,
not complete flight history. Optional map tiles need external network access;
the map controls/markers remain locally served. LAN access scope unchanged; no
public exposure or external notifications added. Full unattended expiry and
reboot verification remain outstanding.
