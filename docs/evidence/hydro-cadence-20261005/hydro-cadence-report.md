# AIS Hydro cadence versus the Opti 10-minute FMI baseline

Analysis retained 2026-10-05T19:51:29+03:00 (Europe/Helsinki). Thomas Vikström.

**Result:** only the Vaasa and Pietarsaari water-level observations demonstrate finer than 10-minute timestamp resolution. Five weather sites provide 10/20-minute timestamp steps, predominantly 20 minutes, and no sub-10-minute observations. Their effective received observation stream is apparently slower than 10 minutes.

**Packet reception frequency ≠ observation update frequency ≠ value-change frequency.**

## Evidence and method

- Snapshot: `logs/ais-type8-raw.jsonl`, 2026-09-24 19:30:23 through 2026-10-05 16:44:24 UTC (22:30:23 through 19:44:24 Europe/Helsinki). 19,362 Message 8 records; 19,356 DAC 1/FID 31 records; all Hydro records use MMSI 2300059. The remaining six are other DAC/FID records.
- Station key is MMSI plus reported latitude/longitude. One MMSI carries seven measurement sites; grouping solely by MMSI would mix their observations. Names use the existing dashboard aliases, with one unmapped coordinate retained explicitly.
- Packet time uses fractional `rxuxtime`; observation time uses encoded UTC `day/hour/minute`. Month/year are resolved to the nearest valid month around reception, including the September/October rollover. One-minute timestamp precision; no encoded seconds.
- Deduplicate by station plus full observation timestamp. Repeated broadcasts do not count as new observations. No contradictory values occurred within any same-station/same-time observation. Round decoded values to four decimal places to remove floating-point representation noise.
- Value-change intervals are time between successive observed change events on the deduplicated series, excluding the first sample as a change. They are not sensor sampling intervals. A constant or quantized value can persist over many new measurements. Missing values are excluded, never converted to zero.
- Quantiles use linear interpolation. All retained gaps are included in main statistics. Receiver rotation currently gives AIS 120 seconds among FM/Tower/ATIS jobs; satellite reservations and reception loss can censor observations. Long gaps establish retained coverage gaps, not station downtime.
- Read-only SQLite inspection corroborates seven locations; its selected-column Hydro table omits observation time and water temperature/visibility. Counts differ slightly from this raw snapshot because recording began before Hydro persistence and live collection continued during inspection. Raw snapshot is authoritative for this analysis.
- Independent NMEA bit decoding checked all 19,356 timestamps and relevant decoded integer fields, with zero mismatches. Water temperature is the unavailable code 501 in every packet. Other unavailable payload fields are detailed in `evidence/hydro-payload-audit.json`.
- Original local snapshot SHA-256: `7c8a2de0a898eecbb78f5d9294451171fd9277fe8c12af20e42d575861e60dfb`. The exact snapshot is retained compressed in `evidence/hydro-raw-snapshot.jsonl.gz`; scripts and JSON results are retained alongside it.

The encoded timestamp and wind averaging meanings follow [IMO SN.1/Circ.289, table 1.1](https://www.e-navigation.nl/sites/default/files/IMO_SN_Circ289.pdf): the timestamp describes the data, while wind speed/direction and gust summarize a 10-minute window. This comparison uses the user-specified 10-minute FMI product baseline; it does not assert that every FMI product has that cadence.

## Station results

All intervals below are minutes. The packet median is about four minutes, while the shortest/common packet spacing is about two minutes.

| Station | Hydro packets | Packet median (p10–p90) | Unique observations | Unique observation median (p10–p90) | Dominant/effective cadence | Repeated packets | Comparison with FMI 10 min |
| --- | ---: | --- | ---: | --- | --- | ---: | --- |
| Unmapped site (62.934883, 21.184851) | 2,790 | 4 (2–6) | 706 | 20 (10–20) | 10/20 min steps; mode 20 min | 2,084 (74.7%) | apparently slower than 10 minutes |
| Maalahti Strömmingsbådan | 2,690 | 3.99 (2–6.01) | 702 | 20 (10–20) | 10/20 min steps; mode 20 min | 1,988 (73.9%) | apparently slower than 10 minutes |
| Vaasa / Vasa | 2,799 | 3.99 (2–6) | 1,788 | 6 (3–10) | 3–6 min typical; mode 6 min | 1,011 (36.1%) | genuinely finer than 10-minute FMI data |
| Mustasaari Valassaaret | 2,770 | 3.99 (2–6) | 697 | 20 (10–20) | 10/20 min steps; mode 20 min | 2,073 (74.8%) | apparently slower than 10 minutes |
| Pietarsaari / Jakobstad | 2,795 | 3.99 (2–6) | 1,788 | 6 (3–10) | 3–6 min typical; mode 6 min | 1,007 (36.0%) | genuinely finer than 10-minute FMI data |
| Pietarsaari Kallan | 2,762 | 4 (2–6) | 700 | 20 (10–20) | 10/20 min steps; mode 20 min | 2,062 (74.7%) | apparently slower than 10 minutes |
| Kokkola Tankar | 2,750 | 4 (2–6) | 688 | 20 (10–20) | 10/20 min steps; mode 20 min | 2,062 (75.0%) | apparently slower than 10 minutes |

## Packet and coverage detail

| Station | Packet min–max | Unique observation min–max | Count at 10 / 20 min | Median observation age at reception |
| --- | --- | --- | --- | --- |
| Unmapped site (62.934883, 21.184851) | 1.99–595.99 | 10–610 | 291 / 355 | 18.39 min |
| Maalahti Strömmingsbådan | 1.98–891.99 | 10–890 | 293 / 353 | 18.4 min |
| Vaasa / Vasa | 1.98–874 | 3–875 | 66 / 0 | 6.4 min |
| Mustasaari Valassaaret | 1.98–874 | 10–880 | 288 / 350 | 18.4 min |
| Pietarsaari / Jakobstad | 1.98–873.99 | 3–875 | 85 / 0 | 6.4 min |
| Pietarsaari Kallan | 1.99–874 | 10–880 | 292 / 354 | 18.39 min |
| Kokkola Tankar | 1.98–874 | 10–880 | 287 / 347 | 18.39 min |

## Variable results

Unique samples means distinct observation times with a valid field; it does not mean distinct numeric values. Changes are detected value transitions. All times are minutes.

| Station | Variable | Unique samples | Changes | Median change interval | Change p10–p90 | Effective resolution | Classification / comment |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| Unmapped site (62.934883, 21.184851) | Wind speed | 706 | 454 | 20 | 10–50 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Unmapped site (62.934883, 21.184851) | Wind gust | 706 | 520 | 20 | 10–42 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Unmapped site (62.934883, 21.184851) | Wind direction | 704 | 633 | 20 | 10–30 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Unmapped site (62.934883, 21.184851) | Air temperature | 706 | 451 | 20 | 10–60 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Unmapped site (62.934883, 21.184851) | Relative humidity | 706 | 475 | 20 | 10–50 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Unmapped site (62.934883, 21.184851) | Air pressure | 706 | 95 | 110 | 30–327 | 10/20 min observations | apparently slower than 10 minutes; 1 hPa quantization; slow changes do not establish slow sensing |
| Maalahti Strömmingsbådan | Wind speed | 702 | 442 | 20 | 10–50 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Maalahti Strömmingsbådan | Wind gust | 702 | 491 | 20 | 10–50 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Maalahti Strömmingsbådan | Wind direction | 702 | 612 | 20 | 10–30 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Maalahti Strömmingsbådan | Air temperature | 702 | 392 | 20 | 10–70 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Maalahti Strömmingsbådan | Relative humidity | 702 | 429 | 20 | 10–60 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Maalahti Strömmingsbådan | Air pressure | 702 | 87 | 110 | 30–400 | 10/20 min observations | apparently slower than 10 minutes; 1 hPa quantization; slow changes do not establish slow sensing |
| Vaasa / Vasa | Water level | 1,788 | 374 | 21 | 6–78.6 | 3–6 min observations | genuinely finer than 10-minute FMI data; 1 cm quantization; unchanged new observations remain valid samples |
| Mustasaari Valassaaret | Wind speed | 697 | 437 | 20 | 10–60 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Mustasaari Valassaaret | Wind gust | 697 | 520 | 20 | 10–50 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Mustasaari Valassaaret | Wind direction | 697 | 606 | 20 | 10–30 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Mustasaari Valassaaret | Air temperature | 697 | 471 | 20 | 10–50 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Mustasaari Valassaaret | Relative humidity | 697 | 455 | 20 | 10–50 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Mustasaari Valassaaret | Air pressure | 697 | 94 | 110 | 30–388 | 10/20 min observations | apparently slower than 10 minutes; 1 hPa quantization; slow changes do not establish slow sensing |
| Pietarsaari / Jakobstad | Water level | 1,788 | 503 | 16.5 | 5–59.9 | 3–6 min observations | genuinely finer than 10-minute FMI data; 1 cm quantization; unchanged new observations remain valid samples |
| Pietarsaari Kallan | Wind speed | 700 | 438 | 20 | 10–60 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Pietarsaari Kallan | Wind gust | 700 | 493 | 20 | 10–50 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Pietarsaari Kallan | Wind direction | 700 | 641 | 20 | 10–30 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Pietarsaari Kallan | Air temperature | 700 | 459 | 20 | 10–50 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Pietarsaari Kallan | Relative humidity | 700 | 481 | 20 | 10–50 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Pietarsaari Kallan | Air pressure | 700 | 106 | 90 | 30–280 | 10/20 min observations | apparently slower than 10 minutes; 1 hPa quantization; slow changes do not establish slow sensing |
| Kokkola Tankar | Wind speed | 688 | 448 | 20 | 10–54 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Kokkola Tankar | Wind gust | 688 | 514 | 20 | 10–40 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Kokkola Tankar | Wind direction | 686 | 604 | 20 | 10–30 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Kokkola Tankar | Air temperature | 688 | 466 | 20 | 10–50 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Kokkola Tankar | Relative humidity | 688 | 453 | 20 | 10–50 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |
| Kokkola Tankar | Air pressure | 688 | 95 | 105 | 30–337 | 10/20 min observations | apparently slower than 10 minutes; 1 hPa quantization; slow changes do not establish slow sensing |
| Kokkola Tankar | Visibility | 680 | 530 | 20 | 10–40 | 10/20 min observations | apparently slower than 10 minutes; No sub-10-minute observation timestamps |

Water temperature: zero available samples at every station → **insufficient data to determine**. Water level is absent at all five weather sites, and wind/air temperature/humidity/pressure are absent at both water-level sites → insufficient data for those station/variable combinations. Visibility is available only at Tankar. Gust direction, dewpoint, pressure/water-level trends, currents, waves, swell, sea state, precipitation, salinity and ice are unavailable in these payloads → insufficient data; no cadence can be inferred from unavailable sentinels.

## Interpretation for Opti

- Water-level timestamp steps are 3, 4, 5 and 6 minutes most commonly (median/mode 6). This supports a roughly five-minute observation stream with minute rounding and missing reports, but does not prove the upstream sensor acquisition schedule. Water-level values also demonstrably change across sub-10-minute observations. Their median change spacing of 21 min (Vaasa) and 16.5 min (Pietarsaari) reflects persistence/1 cm quantization, not a 21/16.5-minute measurement schedule.
- Weather observation timestamps lie exclusively on the ten-minute grid, but generally alternate 10- and 20-minute steps. First reception of a new weather observation has a 16-minute median spacing, with common 14/16-minute spacings; this is consistent with roughly 15-minute source/relay refresh onto a ten-minute timestamp grid. It is an inference, not proof of source internals. No retained weather observation has sub-10-minute spacing. Classify delivered observations as apparently slower than 10 minutes, although the timestamp grid itself is approximately 10-minute resolution.
- Repeated weather broadcasts account for roughly 74–75% of packets, versus roughly 36% for the water-level sites. A ~2-minute broadcast pattern therefore does not imply ~2-minute new measurements. Packet gaps of four/six minutes are common in this rotating receiver setup.
- Median observation age is about 18.4 min for weather and 6.4 min for water level. Frequent receipt is not evidence of fresh source data. For Opti, the demonstrated cadence advantage is limited to water level at these two sites. Weather is useful as a redundant delivery path/spatial source, with no demonstrated temporal advantage over the specified FMI product.
- This establishes the timing of reported observations, not independence from FMI or higher sensor accuracy. An FMI-versus-AIS same-time value comparison and source lineage would be separate work. Preserve both observation and reception times in future Opti ingestion, deduplicate by station/time, and carry freshness/quality flags.

No production service was changed or restarted. Database and production records were read-only; only this documentation, the existing engineering-log/experiments cross-links and standalone analysis evidence were written.
