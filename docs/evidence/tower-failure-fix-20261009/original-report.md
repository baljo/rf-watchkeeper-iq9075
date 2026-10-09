# Tower/AD permanent-failure fix — 9 October 2026

Production worker: `tower_anomaly_shadow.py`.
Installed SHA256: `8ffb0361b5fdf68bafbe6c965b2bc4248583ae31f5f33f9983d5c3a11566437e`.
Rollback copy: `tower_anomaly_shadow.py.bak-failure-fix-20261009`.

The automatic systemd service/timer uses the patched worker. Capture, ASR, model,
threshold, resource guards, service CPU quota, and capture scheduler were unchanged.
The batch bound is five recordings and 45 seconds. Only the AD timer was briefly
paused to replace the file after any active worker finished; no capture service
was stopped.

Completed recordings are checked for missing/empty/zero-frame/truncated audio,
unsupported PCM format, oversize files, and audio shorter than the model's
one-second feature window. Permanent failures are recorded atomically as
`unscorable` under `evaluation/tower-anomaly/shadow/failures/<id>.json`, outside
the original recordings and score files. Original metadata and audio are never
modified. These records are excluded from `pending()`.

Inference/start/I/O failures use per-recording persistent exponential backoff
(60, 120, 240, 480 seconds) and become `failed_terminal/retry_exhausted` on the
fifth failure. Resource preemption gets a 60-second cooldown without consuming
the audio failure budget. Pending includes retry-wait entries until terminal
or scored; eligibility applies the next-retry time. Oldest-first ordering avoids
starvation by new arrivals. Batches continue past item failures, while global
resource deferral stops inference. A process lock prevents overlapping CLI runs.
Unreadable failure state excludes that item rather than resetting its budget.

Initial live baseline at 09:17:16 Helsinki: 96 pending, including fourteen
zero-frame recordings from 5 October. First run reclassified all fourteen and
457 additional historical entries with already-missing audio; a inspected
example had existing `silence_removed` retention metadata. Those 457 entries
were already excluded by the old queue's missing-file filter, so they do not
represent an additional 457-item backlog reduction. Pending fell to 82.
Checksums of all existing 5 October recording files/metadata matched the baseline.

Nine isolated regression tests passed on the EVK. Live automatic runs verified
that newer recordings are scored and resource preemption records cooldown state.
See the private baseline and final JSON evidence for measurements.

To inspect a failure, read its JSON state file. A failed-terminal inference entry
can be retried after the underlying cause is repaired by explicitly clearing
that entry's failure state, preserving its audit record separately. Automatic
workers never clear terminal states. The rollback code predates terminal-state
handling and would need the timer paused before restoring it to avoid the old loop.

## Final live verification

At 09:22:42 Helsinki on 9 October, pending was **86**, with zero 5 October items
pending. The worker's last result was success, its timer active/waiting, and both
scheduler and dashboard active/running. Deployed checksum matched the tested file.
All existing 5 October originals and metadata still matched their baseline hashes.

During 09:17:16–09:22:42 (5 minutes 26 seconds), five new capture directories
arrived and one later recording (`20261009T040032.023314Z`) was scored. Pending
fell from 96 to 82 after removing the fourteen zero-frame entries, then rose to
86 as incoming recordings became eligible. Measured short-window rates were
approximately 0.92 captures/minute versus 0.18 scores/minute. All five completed
worker batches stopped on resource deferral; one scored a recording first and
then cooled down a preempted item. No zero-frame recording was retried.

24 five-second resource samples between 09:20:27 and 09:22:30 showed fourteen
idle samples, six blocked by Tower `rtl_fm` reception at 120.950 MHz, and four
blocked by the shared inference kernel lease. The existing 60-second timer and
10% CPU quota leave scoring vulnerable to starting during occupied intervals
and being preempted before a batch finishes. This measurement demonstrates a
remaining throughput bottleneck; it does not establish a whole-day rate.
Scheduling was not redesigned.
