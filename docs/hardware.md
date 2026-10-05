# Hardware

Verified current inventory and retained receiver evidence, 2026-10-05:

| Component | Identity/use | Evidence/status |
| --- | --- | --- |
| Dragonwing IQ-9075 EVK | `iq-9075-evk`; ARM64 processing host | Existing SSH connection and systemd services; project under `/root/rf-watchkeeper` |
| RTL-SDR Blog V4 | Serial V4MAIN01, R828D tuner | Successful retained IQ preflight diagnostics; FM, Tower, AIS, ATIS and METEOR share this receiver |
| FC0012 sensor SDR | Serial 43300001; 433.920 MHz Nexus-TH | `jobs-sensors.jsonc`, sensor unit and live readings retained since September 24; currently disconnected/disabled in health configuration |
| EVK decoder runtime | SatDump 1.2.2 ARM64 in pinned Debian container | [AUTONOMOUS_EVK.md](../AUTONOMOUS_EVK.md), `data/meteor-native-runtime.json` and native stage artifacts |

Installation region: **Vaasa/Korsholm region, Finland**. Exact observer coordinates remain private on the EVK. Public configuration templates and map centres use approximate example coordinates; see [location privacy](location-privacy.md).

The second-SDR/interference issue remains open: the sensor path and past reception are verified, and the disabled/disconnected state is documented in [RF_HEALTH.md](../RF_HEALTH.md). Retained evidence inspected here does not establish the physical interference mechanism, a controlled comparison, or a verified remedy. Do not describe it as resolved. Antenna model, cabling, filtering and USB topology need an explicit verified hardware inventory.

See [RF jobs](rf-jobs.md), [reliability](reliability.md) and [experiments](experiments.md).

## Publication inspection — 5 October 2026

Qualcomm Linux Reference Distro **2.0**, build `local-20260625153136`; ARM64 kernel **6.18.30-01953-g5086fd78561b-dirty**, SMP PREEMPT build dated 22 June 2026. Read directly from `/etc/os-release` and `uname`, not inferred from product literature. [Inspection evidence](evidence/publication-inspection.json).

USB enumeration showed RTL2838 and Genesys Logic USB2/USB3 hubs. Enumeration alone does not establish detailed cabling/topology or physical serial identity; the configured V4 serial is corroborated by retained capture diagnostics. Antenna model, filtering, cabling and placement remain unverified inventory gaps. Satellite reception is indoor/experimental and variable; weak captures can nevertheless yield useful imagery.
