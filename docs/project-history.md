# Project history

The [engineering log](project-log.md) is the detailed chronological record; this summary preserves its factual dates and uncertainty.

| Date | Milestone |
| --- | --- |
| By 20 September 2026 | Dashboard/saved speech existed; exact initial deployment time unknown |
| 24 September | Nexus-TH sensor reception; AIS integration existed by this date |
| 30 September | Retained V4 IQ verification |
| **1 October 2026** | **Qualcomm approval received, with permission to iterate**; project-owner supplied milestone, no private correspondence published |
| 2 October | Experimental ATIS, older 30-minute interval |
| 3 October | SatDump 1.2.2 ARM64, managed planning and satellite image/history integration |
| 4 October | Schedule/conditions display and persisted capture recovery |
| 5 October | Useful crash imagery, RF watchdog, frequency-aware retention, authorized reviewed cleanup, Tower text/current Airband cadence |
| 5 October, this publication | Existing implementation/docs reconciled with empty canonical GitHub repo; stable docs/source/service snapshots prepared without RF changes |

Approval is owner-provided rather than checked against private email. Other milestones have dated evidence in the log. Current 256 kS/s policy does not replace historical 1.024 MS/s metadata. Older installation guides remain dated snapshots.

## 7–10 October 2026 — current reconciliation

Tower ASR was deferred in favor of acoustic screening, AD shadow diagnostics and human review; 30-day audio/pins replace rolling silence deletion. Tower currently operates 07:00–23:00 Helsinki. ATIS moved to the second compute DSP with cleanup, isolated validation and separate shadow/reference queues; its completed four-hour integrated observation failed acceptance. AIS maps gained dated reception-history selection. Tower review eligibility was tightened to completed above-threshold AD with no human label, and terminal bad-audio retry handling was added.

The Arduino/Qualcomm showcase has been submitted for review. The 10 October audit reconciles repository source/dependencies, service snapshots and current technical guides against the EVK, retaining privacy and explicitly open runtime/reproduction gates. [Current status](current-status.md), [engineering log](project-log.md).
