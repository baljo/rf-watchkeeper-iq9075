> Documentation status, 2026-10-05: Historical October 3 native-runtime installation record. Automation is now enabled and live/future managed sample rate is 256000; see [current METEOR behavior](docs/meteor.md). Preserve original offline validation limits below.

# Autonomous METEOR processing on the EVK

The primary workflow is now entirely on the Dragonwing EVK:

**Plan → reserve V4MAIN01 → existing recorder → EVK SatDump → record outputs → guarded retention.**

Verified 2026-10-03: 27 pipeline/native safety tests passed; the actual EVK ARM64 decoder processed the 402 MiB September 29 M2-4 recording in approximately thirty seconds with exit code zero. It produced no images, matching the Dell result, preserved the original file identity and removed its own temporary container. All original RF services remain active, six original source/config files match pre-edit hashes, existing manual timers remain, and automatic capture/deletion remain disabled. An isolated fifteen-file install/rollback test also preserved manual IQ and modified configuration.

The Dell worker was a temporary bridge and is not required by this configuration. Its Windows task has been removed. No AI or email is needed for core operation. The EVK must remain powered and have internet access for orbital-element refresh; stale elements fail closed.

SatDump 1.2.2 is the official ARM64 package, isolated in a pinned Debian ARM64 container because the Qualcomm host has no compiler or conventional package manager. Dependencies are installed inside that image rather than in the host system. The existing Docker daemon was already active and enabled; no change to its service configuration was necessary. The decoder gets two CPU cores, four GiB memory, a read-only input file, and only its own writable output directory. It has no SDR-device access, network access, elevated capabilities or writable host-system mounts.

`satdump_evk.py` verifies the exact image identity, runs the offline pipeline and cleans up its UUID-named container on completion, interruption or timeout. It leaves original IQ intact. The processing service depends on the existing Docker unit so it is available after reboot. A missing/changed image is reported as unavailable, leaving work queued. Capture planning and raw recording do not depend on the decoder being available; disk-headroom checks prevent uncontrolled storage growth.

Configuration on EVK:

```json
"satdump_command": ["/root/rf-watchkeeper/.satellite-venv/bin/python", "/root/rf-watchkeeper/satdump_evk.py"]
```

The native runtime manifest is `/root/rf-watchkeeper/data/meteor-native-runtime.json`. It records the official package URL/hash, pinned base-image digest, built image ID and wrapper hash. Source definition, package, build log and native wrapper tests are in `/root/rf-watchkeeper/meteor-native-stage-20261003`.

Automation and deletion remain disabled during installation review. Inspect on the EVK with:

```sh
cd /root/rf-watchkeeper
.satellite-venv/bin/python meteor_pipeline.py status
.satellite-venv/bin/python meteor_pipeline.py plan --dry-run
```

Use the existing activation commands in `METEOR_AUTOMATION.md` for the EVK timers only; skip all Dell-task instructions. Automatic retention should remain off until the first automatic pass has been reviewed. The first full live automated capture still needs verification; this update verifies offline decoder operation and reboot configuration without taking the receiver from your existing passes.

Rollback: the install manifest includes the added wrapper and this guide and hashes the updated pipeline/configuration/process unit. The additive installer removes those owned files as described in `METEOR_AUTOMATION.md`, preserving data and modified config backups. The Docker image and runtime manifest remain as recoverable artifacts; they can be removed separately using the exact recorded image ID after processing is disabled. Do not prune unrelated Docker images or containers.

SatDump source: [official 1.2.2 release](https://github.com/SatDump/SatDump/releases/tag/1.2.2). Debian base: `debian:bookworm-slim`, digest `sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251`. SatDump package SHA256: `2630490f0673c189383829e5c4c17c44e2f3c2bedb8ee8747af12586ebf6dbb9`; this is the downloaded package fingerprint, not an upstream-published signature.
