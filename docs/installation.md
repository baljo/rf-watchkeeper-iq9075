# Installation and reproducibility

This exports the existing working EVK application, not an operating-system/model distribution. Preserve any existing deployment rather than overwrite it with a clone.

## Deployed prerequisites

- Dragonwing IQ-9075 EVK, ARM64, Qualcomm Linux Reference Distro 2.0; [hardware](hardware.md) records the kernel.
- V4MAIN01 and installed `rtl_fm`/`rtl_sdr`; optional `rtl_433` and legacy receiver are disabled operationally.
- Native `/root/AIS-catcher`; collector options are in `ais_collector.py`.
- Python with `zoneinfo`, bundled `Helsinki.tzif`, satellite planning environment and NumPy for frequency survey.
- Sibling `/root/sdr_demo/scheduler.py`, preserved as `backends/sdr_demo/scheduler.py`; the application imports it from its parent directory.
- Docker and pinned `rf-watchkeeper-satdump:1.2.2-arm64`, validated against external `data/meteor-native-runtime.json`. [EVK decoder guide](../AUTONOMOUS_EVK.md) preserves runtime construction details.
- Qualcomm ASR binary/libraries in `asr_native/` and Whisper small model in `model-trials/whisper-small-v0.50.2/model`; optional Genie/Qwen3 runtime/configuration under `/root/genie/`.
- Current TLEs, observer settings, systemd dependencies and installed speaker-volume guard/drop-in.

## Deployment approach

1. Preserve source/configuration, units/drop-ins, consistent SQLite backups, metadata, images and recordings; choose a window without satellite reservations.
2. Review code/examples against the target runtime. Application paths expect `/root/rf-watchkeeper`; place the preserved backend at `/root/sdr_demo/scheduler.py` for an equivalent fresh layout.
3. Supply separately installed/licensed binaries/models, satellite environment and validated decoder manifest. Review receiver/observer settings without committing private access material.
4. Compare `deploy/systemd/` with target prerequisites before installing units. Snapshots are evidence, not a complete installer; the speaker guard is external.
5. Validate offline behavior/APIs before enabling ordinary RF. Enable satellite automation only after TLE, disk, manifest and ownership checks. Keep raw deletion disabled until reviewed.

Preserved [METEOR automation](../METEOR_AUTOMATION.md), [ATIS proof of concept](../ATIS_POC.md) and [audio workflow](../AUDIO_WORKFLOW.md) contain dated installation steps. Disabled automation, 1.024 MS/s, 30-minute ATIS and pre-dashboard defaults describe older snapshots; current settings are in [RF jobs](rf-jobs.md) and [METEOR](meteor.md).

A clean-device deployment, packaged installer and model redistribution are not validated here. Public repository visibility does not establish a project license or permission to redistribute proprietary dependencies.
