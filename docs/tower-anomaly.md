# Tower anomaly diagnostics

Current deployed queue handling and operational recovery: [9 October completion audit](tower-failure-fix-20261009.md). This automatic worker supplies shadow diagnostics, preserves originals and excludes terminal bad audio. Throughput and reboot verification remain outstanding.


### 2026-10-09 — Tower candidate threshold queue correction

Deployed: completed valid AD + score >= its recorded model threshold + unreviewed. Voice/uncertain acoustic classifications no longer bypass AD. Twelve tests pass; live queue verified; retention and pins preserved. [Evidence and rollback](tower-threshold-queue-20261009.md). Reboot and extended unattended operation unverified.
