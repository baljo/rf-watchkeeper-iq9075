# ATIS production, shadow ASR and validation

Inspected **10 October 2026**. Capture is **136.450 MHz AM**, 90 s every at least 600 s, all day, 8 kHz PCM and 49.6 dB gain. Shared SDR ownership/METEOR can delay slots. [Scheduling](rf-jobs.md).

## Production processing

`atis_pipeline.py` uses full-message coverage, then `atis_shadow.prepare()` applies the retained full80 preparation (high-pass 80 Hz/resampling and bounded clips). It invokes `atis_runtime_device1.py` from `evaluation/atis-prompt-small-20261007/python/bin/python3`. Qualcomm Whisper Small QCS9075 v0.50.2 encoder/decoder contexts use QNN HTP **deviceID=1**, English, legacy prompt, beam 1. Per-clip original hashes, EOS/execution evidence and runtime logs remain in `runtime-device1/`. `inference_resource.py` holds the shared accelerator lease and prevents concurrent cooperating inference clients.

`atis_parser.py` and `atis_lexicon.py` derive conservative field evidence; raw ASR, normalized text, lexical corrections and field conflicts are preserved separately. Parser `complete` means supported fields were recognized, not that spoken values were correct. Optional Genie uses local `data/atis-genie-device1.json`. Failure preserves base ASR as `partial_success`; numeric/weather fields still require listening review.

`atis_consensus.py` compares only consecutive captures anchored to the newest. Gaps over 900 s, total span over 1800 s, unusable captures, incompatible identifiers or disagreement stop grouping. A selected field needs agreement from two independent captures; older majority voting and digit repair are excluded. Consensus is agreement evidence, not confidence or human truth.

## Separate queues and human references

`rf-watchkeeper-atis-shadow.service` runs `atis_shadow.py` against `data/atis-shadow/jobs.sqlite3`. Enqueue occurs after production publication; shadow outputs never replace production. Eligible saved captures are 3–300 s; bounded holds last at most 48 hours, maximum three attempts, child timeout 180 s. Resource/satellite deferral, restart recovery and failed/completed states remain explicit. The corrected shadow path uses the same device1 runtime; it remains a separately evaluated result.

`rf-watchkeeper-atis-validation.timer` runs `atis_validation.py --sync` every 60 s, discovering candidates without inference. Its human-reference/judgement/audit state is in `data/atis-validation/review.sqlite3`. The dashboard's raw-based strict evaluator is separate from production parsing/consensus. Human annotations must come from listening; the audit invents no reference labels.

## Runtime evidence and current failures

Ten isolated corrected HTP runs passed with identical inputs/reference text, 40 encoder and 4,780 decoder executions and unchanged DMA per process. A scoped CPU/HTP/Tower overlap demo passed. Corrected production and shadow workers are deployed and active. Accelerator execution is therefore evidenced, while whole-device busy percentage, matched speedup and energy benefit remain unverified.

The subsequent four-hour integrated observation **completed but FAILED**: 23/24 verified ASR, only 5/24 complete ASR+Genie, +5,877,841,920 retained DMA bytes and 435 state API timeouts. No later passing acceptance was established. All 12 latest retained outputs inspected on 10 October were partial success with failed Genie interpretation. [Exact quantitative report and closure gates](evk-utilization-status-20261009.md).

## APIs and reproduction limits

`/api/atis` exposes individual/latest/recent captures, raw/normalized text, parser status, counts and consensus. `?recording=<id>` selects a retained capture; `/api/atis/audio` accepts the same selection. `/api/atis/shadow` reports separate queue/results; GET/POST `/api/atis/validation` supports review with token protection on writes.

External candidate Python, QAI AppBuilder, transformers/tokenizer/cache, model context binaries, `evaluation/atis-model-bakeoff-20261007/inputs.json`, candidate `generation_config.json` and Genie config/runtime are **not included**. The public runtime source still refers to these retained operational paths; recreating them needs separately reviewed artifacts, not a fresh clone alone. Do not invoke the runtime casually: it starts inference and requires a lease/safe window. [Installation](installation.md).

[ATIS_POC.md](../ATIS_POC.md) and [5 October text report](evidence/airband-text-20261005/completion-report.md) preserve older paths/30-minute defaults. They do not supersede device1 deployment, the current ten-minute cadence or Tower ASR deferral. Labelled numeric/Finnish accuracy, sustained native reliability, database/positive-audio bounds and reviewed operational alerts remain open.
