# Tower anomaly diagnostics and human review

Inspected 10 October 2026. Tower capture/acoustic classification is independent of ASR; **Tower ASR remains deferred** because current audio is too poor for useful transcription. [Airband](airband.md).

`tower_anomaly.py` computes window-based diagnostic scores using the retained model; the production screening threshold remains **45.67438250526811**. Human review does not automatically retrain/promote a model or alter capture. `tower_anomaly_shadow.py` is an automatic **shadow** worker; model/data artifacts remain private under `evaluation/tower-anomaly/`.

The optional newest-first 20-item review queue requires unreviewed audio with completed valid AD evidence and finite score **>= that evidence's recorded threshold**. Both legacy `candidate_voice` and `anomaly_candidate` query values select this same rule. `voice_candidate` or `uncertain` acoustic states alone do not qualify. Saving any human classification removes the item and refreshes the queue; inclusive history remains available with the filter off. [Threshold queue evidence/rollback](tower-threshold-queue-20261009.md).

Authoritative labels live in `evaluation/tower-anomaly/human-review/*.json`, managed by `tower_anomaly_review.py`. Listening supports voice/no-voice/uncertain judgments; clearer confirmed transmissions can use existing permanent reference pins and future-benchmark marking without starting ASR. `tower_validation.py` recalculates cumulative shadow diagnostics when labels change. Frozen reports are dated observations; this audit does not reuse older label counts as current.

## Worker limits and failure recovery

The installed timer runs 60 s after an inactive worker, with five-second accuracy. The batch drop-in gives a 70 s service timeout; code bounds are five items / 45 s and 15 s per child. CPUQuota=10%, MemoryMax=256M, TasksMax=8, Nice=19 and one BLAS/OMP thread remain. Resource deferral protects primary work; this is not a throughput guarantee.

Missing/empty/zero-frame/corrupt/truncated/unsupported/oversized/too-short audio is terminal `unscorable`. Inference/start/I/O failures back off 60/120/240/480 s and become `failed_terminal/retry_exhausted` at attempt five. Preemption has a 60 s cooldown without consuming audio-failure attempts. Persistent JSON under `shadow/failures/` prevents repeat loops; corrupt state excludes the item rather than clearing retries. Oldest-first batches continue past individual failures.

[9 October failure audit](tower-failure-fix-20261009.md) verified short-window scoring and natural repeated worker launches, but backlog capacity and reboot acceptance remain unresolved. Clearing failure state cannot restore already missing audio. Repair the individual cause, preserve/archive its failure record and retry explicitly; never bulk-clear terminal state. The old rollback worker can reintroduce endless retries.

## Retention and limitations

Audio policy is 30 days with permanent pins/reference trees protected; metadata/classification/labels survive audio expiry. [Retention](data-retention.md). Energy/AD scores do not establish speech intelligibility, reliable anomaly alerts or validated sensitivity/specificity. Human labels remain authoritative; long-run queue throughput, fuller labelled coverage and reboot persistence are open. Source/unit export in this audit mirrors already deployed behavior and makes no new runtime change.
