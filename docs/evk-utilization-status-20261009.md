# EVK utilization / compute evidence: definitive status, 9 October 2026

**Verdict: FAIL for unattended integrated acceptance. This item remains open for Arduino/Qualcomm project documentation.** The narrower corrected accelerated demonstration passed and is suitable for a carefully scoped evidence claim. It does not establish reliable unattended full-pipeline operation or whole-device NPU utilization.

Live inspection began at 17:05 UTC / 20:05 Europe/Helsinki on 9 October. Explicit existing SSH identity restored authorized access after the sandbox initially denied networking. No reconnection or new credentials were needed.

## Which experiment actually finished?

The original combined experiment failed: ATIS child exit -11; METEOR retained replay returned 139 after producing validated PNG products; Tower scoring returned 0. Its old four-hour observer was stopped at 19:16:15 UTC on 7 October after about 84 minutes / 909 samples. It has no completion marker and is a superseded baseline.

The subsequent device1/context-cleanup observation **completed normally but FAILED acceptance**. Window: 7 October 19:54:52–23:54:53 UTC, corresponding to 7 October 22:54:52–8 October 02:54:53 Helsinki. Retained start/finish JSON, 5,398 actual JSONL samples and final report independently agree: 14,401.332 seconds. Observer status 0 means collection completed, not that the workload passed. No later completed acceptance or utilization rerun was found in the live evaluation tree.

## Status distinctions

| Gate | Verified result |
|---|---|
| Isolated corrected HTP path | PASS: 10 consecutive complete processes, identical inputs/gold text, 40 encoder and 4,780 decoder executions, unchanged DMA after each process |
| Heterogeneous CPU/HTP/Tower demonstration | PASS: CPU and HTP process overlap 7.314 seconds; CPU/HTP/Tower exit 0 |
| Deployed | YES: actual automatic production and shadow both invoke `atis_runtime_device1.py`; their live source hashes exactly match fresh-acceptance start hashes |
| Production-active | YES: enabled automatic workers are active; latest retained transcripts identify `device1-cleanup-full80-v2` |
| Unattended integrated acceptance | FAIL: four-hour run completed with pipeline failures and persistent DMA growth |
| Publication-ready evidence | Scoped execution/demo observations only; no reliable full-system, matched-speedup, or total-device utilization claim |

## Quantitative evidence

Corrected isolation: full process wall time median 21.728 seconds, range 20.663–22.101; model time median 19.374 seconds. Reported accelerator graph timings across ten runs: encoder 8,508,998 microseconds; decoder 56,755,031 microseconds. These are graph execution evidence, not device busy percentages. QNN HTP libraries, cdsp1/FastRPC routing and positive execution counters support actual acceleration; mapping libraries alone would not.

For the same retained 28-second WAV, the demonstration observed CPU GGML Small at 148.564 seconds, HTP process at 7.314 seconds (candidate/model 4.891 seconds), one encoder and 115 decoder executions. Tower scorer returned 0 with a 0.528-second reaping bound. Different export/frontend/decoding paths prevent a strict numerical speedup claim. This demonstration did not include simultaneous METEOR decode.

Four-hour corrected automatic run:

- 24 processed ATIS captures: 23 fully verified ASR (95.83%); one incomplete first chunk exhausted its 200-token context (75 prefix + 125 decode positions, no EOS). Shadow: 23 completed, one failed after three attempts.
- Only 5/24 complete ASR-plus-Genie outputs (20.83%); 19 partial results. Genie: 17 exit-1 failures, one timeout, one malformed-JSON rejection.
- No exit -11 in the fresh window; 193 allocation-error log lines, including 58 from Whisper. Successful fallback inference does not clear allocation-error acceptance.
- Idle DMA increased from 11,076,931,584 to 16,954,773,504 bytes: **+5,877,841,920 bytes (5.47 GiB)**. The first persistent increase followed a Genie timeout. Exact native/backend/kernel responsibility is unresolved; global DMA is a retained-mapping indicator, not a measurement of NPU RAM or total utilization.
- ASR elapsed (24 clips, including waits/failed clip): median 30.194 seconds, p95 31.379, maximum 32.289. Capture timestamp to processed output: median 137.497, p95 156.399, maximum 258.947 seconds. The latter includes acquisition and processing; neither is a standalone/concurrent matched latency comparison or hard scheduler-jitter bound.
- State API: 435/5,398 timeouts (8.06%, four-second request deadline). Service activity and a responsive homepage do not establish dashboard interaction reliability.

RF capture completions retained in the final acceptance report: 24 ATIS, 139 Tower, 217 AIS. An independent start-time-bounded SQLite query instead finds 23 ATIS, 139 Tower, 218 AIS; boundary attribution differs, so the cohorts must not be merged. All 380 jobs in that independently queried cohort have `capture_ok=1`, complete timestamps and no recorded same-receiver interval overlap. This does not certify zero dropped opportunities: an expected-job ledger and hard start/deadline comparison are missing. Shared-receiver jobs are time multiplexed; workload integration must not be presented as all RF captures occurring simultaneously.

Actual shadow interruption before the four-hour baseline returned memory to its original idle value and logged cleanup. Existing accelerator leases and METEOR preemption were preserved. No METEOR capture occurred inside the fresh four-hour baseline. Prior deployment evidence recorded a 406,585,344-byte METEOR capture with receiver exit 0 and scheduler restoration, outside that baseline. The latest five retained automatic pass records inspected on 9 October all show capture return 0 and scheduler restored, but two are `decode_failed` and three `decoded_no_products`; they are handoff evidence, not successful image-production acceptance. Latest pass retained 422,313,984 IQ bytes. The separate rtl_433 collector service is inactive at this audit and 433 is absent from the observed acceptance workload; 433 concurrency is unverified and must be stated as excluded.

## Current live verification and preservation

At 17:08 UTC on 9 October, all three acceptance source hashes still match. Latest 12 processed ATIS jobs all remain `partial_success`; every corresponding interpretation failed with `Model exited with code 1`. Eleven transcripts report accelerator verified; one does not. Journals since 15:00 UTC contain 197 `Cannot allocate memory` occurrences, 51 `remote_munmap64 failed` occurrences and three `Incomplete decoder EOS` occurrences. These are log occurrences, not independent failure-job counts. No later repair is established.

Read-only sampling: 82.277 seconds / 36 requests. Aggregate CPU busy mean 6.52%, peak 18.17%; available RAM minimum 24.72 GiB; maximum exposed thermal reading 53.0 C. API median 0.139 seconds, p95 0.290 seconds, maximum 3.612 seconds; zero four-second timeouts. DMA stayed at 5,615,792,128 bytes. Only AIS/AM receiver activity was sampled; no inference was sampled. This short current-boot observation cannot supersede historical retained growth, quantify inference headroom, establish throttle margin, or pass sustained dashboard acceptance. Historical failing 79.4-second combined sample recorded CPU mean 16.78%, peak 43.00%, available RAM 17.13 GiB and maximum temperature 56.3 C; it is not a successful performance baseline.

Read-only SQLite schemas and state were inspected. Frozen shadow queue inventory: 649 total, 258 completed, 391 failed; these historical totals are not fresh-window success rates. Protected original METEOR IQ, ATIS reference WAV and Tower WAV hashes still match. Source/configuration hashes match before/after this audit. No production source, settings, model, ASR, receiver ownership, retention or reviewed label was changed. No reset, restart, reboot or recording deletion was performed. The completed baseline exists, so another diagnostic replay is unnecessary for status determination and would expose the still-failing native path to further retained allocations.

## Exact remaining closure gates

1. Diagnose and safely repair native Genie initialization/timeout/termination retention; clear Whisper allocation/unmap errors and demonstrate stable idle mappings across repeated and preempted integrated jobs. Neither a reboot nor routing to another DSP alone proves a repair. No established safe source-level fix was found during this audit, so no speculative production change was deployed.
2. Resolve incomplete decoder EOS on full live clips without replacing production ASR for a benchmark; verify unchanged references and production/shadow behavior after the repair.
3. Diagnose sustained dashboard state-API timeouts and verify browser/dashboard responsiveness under inference, not only an idle short API sample.
4. Repeat corrected unattended acceptance with a protected scheduled METEOR handoff and successful retained decode as applicable, documented workload exclusions (including 433), expected-versus-actual jobs, preemption/start delay, full pipeline success and stable DSP memory. Retain CPU, memory and thermal telemetry throughout.
5. Obtain representative HTP graph profiling / total-device utilization telemetry where supported and a clearly defined standalone-versus-concurrent latency comparison. Do not invent NPU/DSP occupancy from process overlap or graphs executed.
6. Verify corrected persistence after restart/reboot outside reservations, and retain the required independent ASR accuracy references for broader accuracy/promotion claims. Current boot proves worker routing persisted, not that unattended runtime faults were fixed.

Detailed private evidence on EVK: `evaluation/utilization-audit-20261009/{audit.json,details.json,samples.jsonl}`; historical authoritative evidence: `evaluation/atis-production-device1-20261007/{acceptance-start.json,acceptance-finished.json,acceptance-final.json,acceptance.jsonl}`, `evaluation/atis-segv-20261007/{verified-validation.json,demo-summary.json}`. No precise home coordinates or private raw journals are included in this public report.

Completion check: live inspection, exact evidence, preservation, shared report/change-log update and scoped Git commit performed; production rollback not applicable because runtime was unchanged. Reverting this documentation commit or restoring its private documentation backups rolls back reporting changes only. Native repair, passing integrated rerun, sustained response and restart/reboot acceptance remain unmet. Public publication is recorded separately and must not be inferred from a local commit.
