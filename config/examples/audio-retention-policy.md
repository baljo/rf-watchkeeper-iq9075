# Audio retention configuration

Authorized production defaults, 14 October 2026: `tower_retention.py` defines `RETENTION_DAYS = {'tower': 14, 'atis': 7}`. `DAYS`/`SECONDS` are compatibility constants for Tower. No receiver/job config change or database migration is needed. There is no filesystem mtime fallback. Original UTC capture folder IDs supply the recording time; malformed/missing capture provenance is retained with errors, never guessed.

Install `deploy/systemd/rf-watchkeeper-audio-retention.service` and `.timer` into `/etc/systemd/system/`, then:

```sh
cd /root/rf-watchkeeper
python3 tower_retention.py daily --dry-run
systemctl daemon-reload
systemctl enable --now rf-watchkeeper-audio-retention.timer
systemctl start rf-watchkeeper-audio-retention.service
journalctl -u rf-watchkeeper-audio-retention.service
```

The timer runs daily at **02:30 UTC** (05:30 EEST / 04:30 EET), with `Persistent=true` for a missed run, timeout 600 seconds and private umask 0077. It remains enabled during acquisition suspension. There is no competing age cleanup in processing workers. Existing satellite cleanup scheduling/policy is unchanged.

Only ordinary WAV files directly inside valid live `recordings/tower/<UTC-ID>` and `recordings/atis/<UTC-ID>` folders expire. Pinned/Keep/protected/reference markers, explicit capture reference flags and `atis-human-reference.json` protect indefinitely; reference/evaluation trees and symlinks are outside deletion scope. Pending review, bounded human validation holds, terminal failures and missing legacy `processed.json` do not extend the age cap. Genuine processing calls use `.audio-processing.lock`; cleanup takes it nonblocking and also checks process arguments/open readers. Waiting queue entries do not hold forever. Protection and metadata errors retain audio. Global inventory/lock failures abort a category and exit nonzero. Per-record failures are logged and retained while safe records still expire; the service can complete successfully with nonzero per-record error counters.

Summary fields per category: `eligible`, `protected`, `deleted`, `errors`, `bytes_freed`, `would_free_bytes`, `error_details`, `fatal`; file counters and folder protection counters have different units. A separate `tower-retention-policy.json` records expiry for either category. DB rows, capture/processing/transcript/classification/review/reference metadata are never removed. Original filenames remain as historical provenance after their audio disappears. Clip ASR JSON/log outputs are now preserved; temporary inference WAVs can still be removed after processing. ATIS no-activity originals follow the same seven-day age policy.

Existing permanently referenced clips remain protected. Metadata already deleted by historical clip cleanup cannot be recreated. Three historical Tower folders have malformed/missing capture JSON and are retained fail-closed (225,324 surviving audio bytes at verification); incomplete current captures can briefly appear in the same counters. Counts are dated observations, not a quota. See [verification](../../docs/evidence/retention-suspend-20261014/completion.md) and [operator suspend/resume commands](../../docs/acquisition-mode.md).
