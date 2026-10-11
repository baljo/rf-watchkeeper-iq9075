# Tower anomaly diagnostics and human review

Inspected 10 October 2026. Tower capture/acoustic classification is independent of ASR; **Tower ASR remains deferred** because current audio is too poor for useful transcription. [Airband](airband.md).

`tower_anomaly.py` computes window-based diagnostic scores using the retained model; the production screening threshold remains **45.67438250526811**. Human review does not automatically retrain/promote a model or alter capture. `tower_anomaly_shadow.py` is an automatic **shadow** worker; model/data artifacts remain private under `evaluation/tower-anomaly/`.

The optional newest-first 20-item routine queue uses `tower_review_policy.py`, independently of the detector. The detector/scientific threshold remains **45.67438250526811 (45.6744)**; no retraining or threshold change occurs. Unreviewed clips require completed finite AD evidence and available audio. Peaks below the detector threshold are hidden; peaks from the detector threshold to <55 are hidden except for a deterministic audit. Peaks >=55 require two successive valid 1-second windows each >=55 with starts 0.5 seconds apart (tolerance 1e-6 seconds). Missing/malformed windows, gaps, duplicate/reversed starts and isolated spikes do not establish persistence.

Audit membership is SHA-256 of UTF-8 `tower-grey-audit-v1:` plus capture ID, interpreted as an unsigned big-endian integer, modulo 100 <8. This targets 8% without reselecting on refresh or review; finite datasets may differ. Existing explicit Tower pins and capture metadata `pinned`, `reference`, `permanent_reference`, `reference_sample` or `review_override` true bypass the routine gate but still require AD evidence, audio and an unreviewed state. Informative validation/reference-review paths remain separate and available. Both legacy query values select this same policy. Saving a label refills the queue. Filter-off history and all retained diagnostics remain available. This is queue selection only; it never changes scientific validation, capture, retention, ASR or worker scheduling. [Deployment, census and rollback](evidence/tower-review-policy-20261011/completion.md).

Authoritative labels live in `evaluation/tower-anomaly/human-review/*.json`, managed by `tower_anomaly_review.py`. Listening supports voice/no-voice/uncertain judgments; clearer confirmed transmissions can use existing permanent reference pins and future-benchmark marking without starting ASR. `tower_validation.py` recalculates cumulative shadow diagnostics when labels change. Frozen reports are dated observations; this audit does not reuse older label counts as current.

## Worker limits and failure recovery

The installed timer runs 60 s after an inactive worker, with five-second accuracy. The batch drop-in gives a 70 s service timeout; code bounds are five items / 45 s and 15 s per child. CPUQuota=10%, MemoryMax=256M, TasksMax=8, Nice=19 and one BLAS/OMP thread remain. Resource deferral protects primary work; this is not a throughput guarantee.

Missing/empty/zero-frame/corrupt/truncated/unsupported/oversized/too-short audio is terminal `unscorable`. Inference/start/I/O failures back off 60/120/240/480 s and become `failed_terminal/retry_exhausted` at attempt five. Preemption has a 60 s cooldown without consuming audio-failure attempts. Persistent JSON under `shadow/failures/` prevents repeat loops; corrupt state excludes the item rather than clearing retries. Oldest-first batches continue past individual failures.

[9 October failure audit](tower-failure-fix-20261009.md) verified short-window scoring and natural repeated worker launches, but backlog capacity and reboot acceptance remain unresolved. Clearing failure state cannot restore already missing audio. Repair the individual cause, preserve/archive its failure record and retry explicitly; never bulk-clear terminal state. The old rollback worker can reintroduce endless retries.

## Retention and limitations

Audio policy is 30 days with permanent pins/reference trees protected; metadata/classification/labels survive audio expiry. [Retention](data-retention.md). Energy/AD scores do not establish speech intelligibility, reliable anomaly alerts or validated sensitivity/specificity. Human labels remain authoritative; long-run queue throughput, fuller labelled coverage and reboot persistence are open. Source/unit export in this audit mirrors already deployed behavior and makes no new runtime change.
