# Installation and reproducibility

**A fresh clone is not a turnkey EVK image.** This repository exports the working application, not an operating system, model distribution or complete installer. Binaries, models, runtime manifests, databases and recordings are excluded. Clean-device deployment and a packaged installer have not been validated.

Use section A for a new device and section B for maintenance. Do not overwrite an existing deployment with a clone. This guide was reconciled with repository source and dated evidence on 9 October 2026. Follow-up live inspection succeeded after explicitly selecting the existing SSH key; dashboard/scheduler/processing/health timer were active and state/schedule APIs returned HTTP 200. This verifies the existing deployment, not a clean-device installation.

## A. Fresh installation / reproduction for an external IQ-9075 user

Follow the steps in order. Commands describe the expected Linux layout and inspection paths. Host package installation commands are omitted where no verified procedure is documented. If a prerequisite is unavailable, record the gap and stop that workload's setup rather than treating it as installed.

### 1. Establish the starting point

The recorded platform is a Dragonwing IQ-9075 EVK, ARM64, running Qualcomm Linux Reference Distro 2.0; [hardware](hardware.md) records the kernel and antenna limitations. Provision the board/OS using the supported vendor process first. This repository does not flash the board or install USB drivers, Docker, Python or Qualcomm runtimes.

You need administrative access, systemd, a synchronized clock, writable local storage and a trusted LAN for the dashboard. METEOR also needs current TLEs/internet access and substantial IQ storage: the example requires 10 GiB free **after** estimated capture storage. Attach an RTL-SDR Blog V4 and suitable antenna. Exported jobs expect serial `V4MAIN01`; match your actual serial consistently in jobs, health and METEOR configuration. One V4 is shared by Tower, ATIS, AIS and reserved METEOR capture. Do not run competing receivers.

### 2. Clone and establish application/backend placement

On a **new device with no existing `/root/rf-watchkeeper`**, using separately installed Git and authorized repository access:

```sh
git clone https://github.com/baljo/rf-watchkeeper-iq9075.git /root/rf-watchkeeper
cd /root/rf-watchkeeper
git rev-parse HEAD
```

Record the revision. Units and the SatDump wrapper expect `/root/rf-watchkeeper`; relocation requires a full path review. Read [AGENTS.md](../AGENTS.md) and [workflow](workflow.md) before engineering changes.

`job_manager.py` imports `sdr_demo.scheduler`. The preserved backend is [backends/sdr_demo/scheduler.py](../backends/sdr_demo/scheduler.py); code searches the application parent before the bundled `backends` directory. For equivalent deployed placement, supply a reviewed copy at `/root/sdr_demo/scheduler.py`. A fresh checkout can also resolve the bundled backend. Check which copy loads: an existing sibling can override it. Never overwrite a sibling backend without comparison and backup.

### 3. Supply SDR dependencies

Install V4-compatible RTL-SDR tools using a procedure supported by your OS/device. `rtl_sdr` provides raw satellite IQ and `rtl_fm` provides AM audio; both must be on the service PATH and able to access USB. No verified fresh-host package/build recipe or pinned RTL-SDR version is supplied. Do not assume conventional host package-manager commands work on the recorded Qualcomm distro.

AIS expects native ARM64 `/root/AIS-catcher`. Review [ais_collector.py](../ais_collector.py) and [AIS](ais.md): dual-channel reception, JSON `-o 5`, automatic tuner gain, RTL AGC and 192K bandwidth. Obtain/build it separately and verify compatible options; its exact version and fresh-device build are not recorded here. Optional `rtl_433` supports the historical [433 MHz](433mhz.md) path, which remains disabled and is not required for primary V4 operation.

Inspect executable availability without opening RF:

```sh
command -v rtl_sdr rtl_fm
test -x /root/AIS-catcher
```

Before services/reservations exist, use your platform's USB inspection tools and a controlled receiver test to confirm the V4 serial and actual sample progress. Enumeration alone is insufficient. Do not run an unbounded receiver test alongside scheduling/capture. [RF health](../RF_HEALTH.md) separates sample evidence from decoded traffic.

### 4. Supply Python environments

Ordinary snapshots use `/usr/bin/python3`; METEOR uses `/root/rf-watchkeeper/.satellite-venv/bin/python`. Supply Python supporting `zoneinfo` and Linux `fcntl`, with `Europe/Helsinki` timezone data; the application also includes `Helsinki.tzif`. The planner imports `requests` and `skyfield`; frequency survey needs NumPy. Install these in the satellite environment through your supported provisioning process, and check imports under each service interpreter.

No dependency lockfile or verified clean-device environment creation recipe is included. Windows checks cannot replace Linux/ARM64 validation. Once the environments exist:

```sh
/usr/bin/python3 -c 'from zoneinfo import ZoneInfo; import fcntl; print(ZoneInfo("Europe/Helsinki"))'
.satellite-venv/bin/python -c 'import requests, skyfield, numpy; from zoneinfo import ZoneInfo; print(ZoneInfo("Europe/Helsinki"))'
```

Expected: imports succeed under the interpreters the units actually execute.

### 5. Create local configuration and review RF settings

Only on a fresh checkout, after checking neither destination exists:

```sh
cp -n ais-config.example.json ais-config.json
cp -n meteor-config.example.json meteor-config.json
```

Edit the ignored local copies. **The METEOR example has `enabled: true`: set it to `false` before starting automation.** Keep `cleanup_enabled: false` and `retention.automatic_deletion_validated: false`. Enter actual observer coordinates/elevation locally; public examples are not planning/distance calibration. Review the dashboard's example observer/map centres separately. Keep private edits out of Git, patches, screenshots and evidence: ignored JSON does not protect tracked HTML. See [location privacy](location-privacy.md).

Review `jobs-v4.jsonc`, `rf-health-config.json`, device serials, paths, ownership, frequencies and gains against your site. Vaasa/Korsholm Tower/ATIS examples are location-specific. [RF jobs](rf-jobs.md), [Airband](airband.md) and the latest log describe subsequent decisions: Tower ASR is deferred because current audio is too poor for useful transcription. Do not reinstate it from historical instructions. Keep optional 433 and legacy standalone receivers disabled and preserve METEOR priority.

### 6. Supply external ASR, Whisper and optional Genie

The speech path uses Qualcomm `asr_native/voice-ai-ref` and libraries in `asr_native/`, plus Whisper small QCS9075 v0.50.2 at `model-trials/whisper-small-v0.50.2/model`. These are excluded. Obtain compatible binaries/libraries/models separately under their applicable access and licensing terms. Review [asr_offline.py](../asr_offline.py) and [ATIS](atis.md), then validate a known local saved-audio control before RF speech processing.

Optional Genie/Qwen3 lives under external `/root/genie/`, with recorded config `/root/genie/qwen3-4b-iq9075/genie_config.absolute.json`. Retained runs fail; optional interpretation failure must remain visible while valid base transcripts survive. The corrected device1 ATIS path has measured graph-execution evidence; saved-audio requests alone do not prove acceleration or performance. Missing speech dependencies prevent full text reproduction even when capture/dashboard work. Public repository visibility establishes neither a project license nor redistribution permission for proprietary dependencies/models.

### 7. Supply SatDump ARM64/Docker runtime

The recorded decoder is **SatDump 1.2.2 ARM64**, isolated in `rf-watchkeeper-satdump:1.2.2-arm64` on Debian `bookworm-slim`, rather than installed on the Qualcomm host. [AUTONOMOUS_EVK.md](../AUTONOMOUS_EVK.md) records the base digest, downloaded package fingerprint and October 3 offline validation. [Current METEOR](meteor.md) documents subsequent useful imagery and unresolved SIGSEGV.

Docker already existed on the original EVK. The build definition/package/log were retained externally in `/root/rf-watchkeeper/meteor-native-stage-20261003`, absent from Git. Required `data/meteor-native-runtime.json` is also excluded. Recover reviewed artifacts or independently construct and validate an equivalent runtime before claiming decoding available. The package fingerprint is not an upstream signature. A matching tag is insufficient: [satdump_evk.py](../satdump_evk.py) compares Docker's actual image ID with manifest `image_id`. Do not blindly copy another host's identity or bypass this check.

Preserve the wrapper's two-CPU/four-GiB limit, no network/SDR access, read-only IQ, dedicated output mount and cleanup of only its UUID-owned container. Config selects the wrapper through `.satellite-venv`, empty `satdump_prefix` for the 1.2.2 CLI, `meteor_m2-x_lrpt`, unsigned `cu8` and explicit M2-3/M2-4. Decode each recording at its actual sample rate. Future managed examples use 256000, not historical 1024000. Newer SatDump compatibility is unvalidated.

### 8. Review and install systemd units in stages

[deploy/systemd](../deploy/systemd/) contains inspected snapshots, not a complete installer. Review every selected unit's `ExecStart`, dependencies, drop-ins, interpreter and writable paths before copying it into `/etc/systemd/system/`. Prefer these snapshots to older duplicate root units. Existing deployments must use section B.

For example, after review on the new host:

```sh
cp deploy/systemd/rf-watchkeeper-dashboard.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now rf-watchkeeper-dashboard.service
```

Use the same explicit-file review/copy/reload pattern for required units; do not bulk-enable the directory. Start dashboard first, then primary scheduler only after RF/ownership prerequisites pass. Add ATIS processing only after its dependencies are validated. The recorded scheduler has an external drop-in requiring a 30% speaker guard, absent from this export. The legacy interpreter and scheduler speaker-volume drop-in are now exported snapshots; the guard implementation remains external. Reconstruct/review missing dependencies rather than claiming a complete service reproduction.

Review METEOR plan/dispatch/process/cleanup timers, capture and boot recovery together; keep capture disabled while validating. Historical stage installers are not included: do not invoke their paths as fresh-install commands. Health/preflight recovery can affect RF and ultimately request reboot; read [watchdog/recovery](watchdog-and-recovery.md) before enabling. Keep standalone AIS/legacy Watchkeeper and optional sensors disabled: ordinary AIS belongs to the scheduler.

### 9. Validate initial operation and expected results

Start with checks that do not open RF:

```sh
cd /root/rf-watchkeeper
/usr/bin/python3 job_manager.py --config jobs-v4.jsonc --dry-run
.satellite-venv/bin/python meteor_pipeline.py status
.satellite-venv/bin/python meteor_pipeline.py plan --dry-run
systemctl status rf-watchkeeper-dashboard.service rf-watchkeeper-scheduler.service
systemctl list-timers --all
journalctl -u rf-watchkeeper-scheduler.service -n 50 --no-pager
curl -f http://localhost:8080/api/state
curl -f http://localhost:8080/api/tower
curl -f http://localhost:8080/api/atis
curl -f http://localhost:8080/api/meteor/schedule
```

Planner dry-run can refresh the TLE cache but does not save a plan or take SDR ownership. Privately check observer settings, UTC/Helsinki times, correct NORAD identities, TLE freshness through the entire window, plausible geometry, disk headroom and manual reservations. An empty valid plan can be normal; stale elements must fail closed. Review the 36-hour window, 10-degree horizon, 25-degree minimum peak and south-sector filter for your site; four passes are a limit, not a guarantee.

After enabling ordinary scheduling in a clear window, observe normal slots instead of launching a second receiver:

| Check | Expected result / limit |
| --- | --- |
| SDR | Correct device, actual sample progress, bounded children and no simultaneous ownership |
| Dashboard | Trusted-LAN `http://<EVK-address>:8080`, working panels/APIs; fresh histories can be empty |
| Scheduler | Jobs/logs advance; intentional METEOR delay/skip is normal |
| AIS | Native samples and, with usable reception, stored targets/history in `/api/state`; no `/api/ais` or guaranteed vessel count |
| Tower/ATIS | Capture metadata/status and available audio; quiet/pending/interrupted/failed states remain distinct. ATIS text requires ASR; Tower ASR remains deferred |
| METEOR | Plausible dry-run/status; missing runtime/image mismatch explicit. Successful decode alone does not guarantee imagery |

Listen to captures and compare known controls before claiming speech accuracy. Quiet/poor RF is not a positive speech test. [Testing](testing-and-validation.md) separates simulation, offline decoding, deployed observations and outstanding hardware acceptance; see [troubleshooting](troubleshooting.md).

### 10. Enable unattended operation after review

After planning, ownership, storage and decoder checks pass, set local METEOR `enabled` true and follow the reviewed EVK timer activation sequence in [METEOR_AUTOMATION.md](../METEOR_AUTOMATION.md). Ignore its obsolete Dell worker, initially disabled deployment and 1.024 MS/s defaults. Keep both deletion gates false; failed/unverified raw captures must not be automatically deleted. [Retention](data-retention.md) governs later review; disk pressure skips capture rather than authorizing deletion.

Keep the EVK powered. Record normal scheduled Tower/ATIS/AIS operation, a managed satellite handoff/capture/process result, scheduler restoration and post-restart persistence. Inspect journals, pass records and free storage without interrupting reservations. Schedule reboot acceptance outside capture windows. Real watchdog reboot/end-to-end resume and sustained unattended reliability remain outstanding in retained evidence; enabled units prove neither. See [operation](operation.md) and [reliability](reliability.md).

## B. Updating an existing RF-Watchkeeper deployment

### 1. Inspect and preserve the operational source of truth

The live `/root/rf-watchkeeper` tree is authoritative; GitHub may lag operational edits. Inspect source/config, installed units **and drop-ins**, service/timer state, ownership/reservations, logs and shared records before changes. Choose a window without active/imminent satellite or inference work. Do not force RF probes, stop capture or reboot to close a documentation gate.

Back up affected source/configuration and sibling backend, units/drop-ins, consistent SQLite backups, metadata, recordings, images and external runtime identities. Keep private backups/evidence on the EVK. Record prior revision/hashes and affected services for rollback; avoid inconsistent copies of databases being written.

### 2. Stage and reconcile the update

Use a separate checkout/staging directory and compare selected changes with the live tree. Preserve unrelated edits, private observer JSON/dashboard centres, jobs, model paths, speaker guard, pinned manifest/image and reservations. Do not replace the application wholesale, copy config examples again, or blindly pull over a modified deployment. Preserve Tower ASR deferral, 30-day Tower audio retention/pins and METEOR failed/unverified raw preservation. Dated historical guides do not override these decisions.

### 3. Validate and install only selected files

Run appropriate offline tests and Markdown/link checks first. Review the diff for private locations, secrets and generated/large files. Install only reviewed changes; reconcile units/drop-ins before `daemon-reload`, restarting only affected services in the safe window. Never bulk-enable snapshots or restore an old whole-project folder over newer data. Documentation-only edits require no RF setting, service restart, timer or database change.

If validation fails, restore specifically backed-up affected code/units, preserve newer local configs/data and restart affected services when safe. Historical installer rollback commands apply only when their original stage/manifest exists and matches the installation.

### 4. Verify and record completion

Repeat relevant section A status/API/planner checks. Confirm scheduled work resumes, METEOR priority/deletion gates remain intact and prior data/pins survive. Verify relevant restart/reboot persistence when safe or explicitly report it unverified. Read live records for counts, not historical totals. Append a dated [engineering log](project-log.md) entry with files, rationale, exact validation, rollback and remaining gates; save sanitized evidence, update affected current guides and commit/publish through [workflow](workflow.md).

## Remaining reproducibility limitations

Preserved [ATIS proof of concept](../ATIS_POC.md) and [audio workflow](../AUDIO_WORKFLOW.md) provide dated installation/rollback context alongside the METEOR guides. Their 30-minute ATIS interval, pre-dashboard defaults and stage-specific installers are historical; current guides and local configuration take precedence.

- Fresh OS provisioning, SDR/AIS-catcher installation and exact versions, and locked Python dependencies lack an end-to-end validated recipe.
- Docker provisioning, original image build stage/runtime manifest, proprietary ASR/Whisper/Genie artifacts, speaker guard/drop-ins require separate acquisition/reconstruction.
- No clean-device acceptance run occurred for this revision. Follow-up access resolved the initial SSH authentication gap; only documentation was synchronized to the EVK, with no runtime deployment or restart.
- ATIS/numeric/Finnish accuracy, QNN whole-device utilization and comparative performance remain unverified; Tower ASR is deferred. Genie failures and SatDump SIGSEGV remain unresolved. Retained useful crash products do not mean the decoder is repaired.
- Real reboot recovery and sustained unattended RF reliability remain operational gates. This remains an application export, not a turnkey installation.

## Deployed-source reconciliation — 10 October 2026

This export now includes device1 ASR/resource-lease, ATIS shadow/parser/lexicon/consensus/validation, Tower classification/retention/cumulative-validation dependencies and current speech/diagnostic unit snapshots. Earlier source alone did not reproduce the deployed paths. Prefer `deploy/systemd/` snapshots plus reviewed drop-ins to root historical unit copies. No runtime reinstall or service restart was required: these files already run on the EVK.

The production ATIS worker invokes `evaluation/atis-prompt-small-20261007/python/bin/python3` and `atis_runtime_device1.py`, with QAI AppBuilder, transformers, tokenizer/cache, QNN context binaries and candidate configuration. It also reads `evaluation/atis-model-bakeoff-20261007/inputs.json` and candidate `generation_config.json`; Genie uses `data/atis-genie-device1.json`. These external artifacts remain excluded and must be supplied/reviewed separately. The prior voice-ai-only instructions apply to the preserved saved-audio path, not current production ATIS. [Actual flow and limits](atis.md).

Current installed Tower window is 07:00–23:00 Europe/Helsinki, with an optional local pause-until file. Tower ASR is deferred and audio policy is 30 days/pins; AD shadow requires a separately supplied `evaluation/tower-anomaly/model.json`. Exported scheduler speaker-volume drop-in refers to an external guard; it must be supplied before enabling the scheduler. The new shadow/validation units are snapshots to review individually, not a bulk activation instruction.

Actual HTP execution is evidenced in corrected isolated runs and both ATIS workers are active, but integrated acceptance failed. Do not interpret a fresh import/unit check as native-runtime reliability or accuracy acceptance. [Current status](current-status.md), [utilization evidence](evk-utilization-status-20261009.md).
