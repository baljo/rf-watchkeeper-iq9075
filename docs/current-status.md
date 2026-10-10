# Current project status — 10 October 2026

Live inspection snapshots began 06:49 UTC / 09:49 Europe/Helsinki; detailed follow-up at 06:55 UTC / 09:55 Helsinki. Canonical repository baseline: `bf0edb702790a06b9f1923ebc6346d2e9001de60`. Arduino/Qualcomm showcase **submitted for review**; review submission is distinct from operational acceptance.

## Verified deployed state

| Area | Current result |
|---|---|
| Platform | Dragonwing IQ-9075 EVK, Qualcomm Linux Reference Distro 2.0, ARM64 |
| SDR | One V4MAIN01 shared by Tower/ATIS/AIS; METEOR has reservation priority; ordinary backends serialized |
| Tower | 120.950 MHz AM; 15 s probes / nominal 60 s starts / 10 s tail / 75 s maximum; 07:00–23:00 Helsinki; ASR deferred; acoustic screen plus separate AD shadow |
| ATIS | 136.450 MHz AM, 90 s / at least 600 s all day; device1 HTP full80 path deployed in production and separate shadow; parser/consensus/reference queues |
| AIS | Dual channel; home workload with <=45 s chunks shortened for due Airband; reception-history map selection |
| METEOR | Enabled 256 kS/s, 137.900 MHz, 49.6 dB gain; existing planning/margins/retries and SatDump partial-success behavior; deletion gates false |
| 433 / FM | Optional 433 receiver and periodic FM disabled; historical data preserved |
| Services | Scheduler, dashboard, production ATIS, shadow ATIS and legacy interpreter active; health, METEOR, Tower shadow and ATIS validation timers active |
| Audio/IQ | Tower 30-day policy with permanent pins; failed/unverified satellite raw not automatically deleted; ATIS/database bounds remain incomplete |

The retained Tower pause-until file expired on 8 October at 23:00 Helsinki. It is historical temporary state, not a current pause. Human Tower review at the follow-up snapshot contained **111 labels**: 43 confirmed_voice, 61 no_voice, 3 probable_voice, 2 interference, 1 carrier_or_squelch, 1 unclear. These are dated label observations, not claimed accuracy or fixed current totals. The audit created no labels or pins.

Raw satellite inventory: **31 cu8 / 18,356,895,744 bytes**. Approximate installation wording only: **Vaasa/Korsholm region**. Private observer/config/API snapshots stay outside public Git.

## Reliability and publication claims

Ten corrected isolated HTP processes and the scoped CPU/HTP/Tower overlap demo passed. Both automatic ATIS workers are deployed/active. The corrected **four-hour integrated run completed but FAILED**: 23/24 verified ASR, 5/24 complete ASR+Genie, +5,877,841,920 retained DMA bytes, 435 state API timeouts. No later passing unattended run was established. [Definitive evidence and quantitative limits](evk-utilization-status-20261009.md).

At the audit snapshot, all 12 latest retained ATIS outputs were `partial_success` with failed Genie interpretation and device1 runtime identity. `/api/state` timed out at 10 s; Tower/ATIS/METEOR/schedule/audio returned 200. Follow-up state calls recovered (three 200s around 0.135 s), while validation/review APIs each timed out at 4 s. Active service state does not imply responsiveness or semantic success.

## Known limitations and unresolved work

- **Native/DMA/Genie:** safe permanent native allocation/mapping repair remains unresolved; corrected isolation does not establish integrated reliability. Preserve logs/originals, diagnose the cause and require a new passing unattended run. No production substitution/reset/reboot was performed for this audit.
- **Dashboard:** state and review endpoint timeout behavior remains unresolved. Subsequent quick state responses do not close the issue.
- **Tower retention enforcement:** `tower_retention.cleanup()` requires legacy `processed.json`; new acoustic-only records may have only `tower-classification.json`, and the current worker does not periodically call Tower cleanup for every such record. The 30-day policy is documented but a complete archive bound is not established. A separately tested production retention change is required; this audit preserves existing behavior/pins.
- **Tower queue/capacity:** resource-deferred AD backlog/long-run throughput and labelled calibration remain open. Filter eligibility is completed valid above-threshold AD plus unreviewed, not acoustic status alone. Missing older audio cannot be restored by retry-state clearing.
- **ATIS:** numeric/field/Finnish accuracy, fuller human references, reviewed alert behavior and bounded positive-audio/database retention remain open. Parser/consensus completeness is not confidence or truth.
- **METEOR:** underlying SatDump SIGSEGV, indoor pass-by-pass image quality and stronger frequency acquisition evidence remain unresolved. Useful products preserve partial success, not decoder repair. No automated failed/unverified raw deletion.
- **Hardware/recovery:** optional second-SDR interference cause/remedy, exact physical antenna/cabling inventory and real new-watchdog reboot/end-to-end resume remain unverified.
- **Reproduction:** clean-device provisioning, dependency pinning, external Qualcomm/candidate/model/cache/config and pinned SatDump build artifacts remain outside the repo. Source/unit snapshots are not a turnkey image or fresh-install acceptance.

## Repository reconciliation and drift disposition

The audit exports already deployed source for device1/resource control, ATIS parser/consensus/shadow/validation and Tower classification/retention/validation; updates current dashboard/capture/source and installed unit/drop-in snapshots; refreshes all current topic guides and README. **No new runtime source deployment is needed** because exported behavior already exists on the EVK. Only documentation/shared log synchronization is required.

Export privacy changes use approximate map centres/test observer fixtures, omit private coordinates/session tokens, and normalize four invalid UTF-8 dashboard characters. Public AIS tests retain newer reception-history coverage absent from the older live test. Superseded acoustic-queue tests and one-off historical review/cleanup/collection scripts remain EVK-only, explicitly recorded in [inspection](evidence/repository-audit-20261010/inspection.json). Older root units and staged/historical guides are labeled historical; use current `deploy/systemd/` snapshots and topic docs.

Historical engineering-log links to excluded data/backups/stages describe retained EVK-only evidence; they are not fresh-clone commands. Historical chronology is preserved and corrected by the new dated entry, rather than silently rewritten. [Publication manifest](publication-manifest.md).

Verification, exact changed-file inventory, skipped checks, rollback and standing-rule completion are recorded in [audit completion](evidence/repository-audit-20261010/completion.md). Runtime reliability/fresh-install/reboot gaps remain explicitly open even when documentation/publication is complete.
