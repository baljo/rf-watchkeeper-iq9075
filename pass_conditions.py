"""Retained capture facts and orbital predictions, independent of decoding."""
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent


def recorded(metadata, planned=None):
    p = planned or {}
    result = dict(metadata.get('pass_conditions') or {})
    fields = {'start': ('pass_start_10deg', 'start'), 'stop': ('pass_stop_10deg', 'stop'),
              'record_start': ('record_start', 'record_start'), 'record_stop': ('record_stop', 'record_stop'),
              'gain': ('gain_db', 'gain'), 'device': ('device_serial', 'device'),
              'frequency': ('frequency_hz', 'frequency'), 'sample_rate': ('sample_rate_sps', 'sample_rate'),
              'pre_margin': ('pre_margin_seconds', 'pre_margin'), 'post_margin': ('post_margin_seconds', 'post_margin')}
    for key, (capture_key, plan_key) in fields.items():
        value = metadata.get(capture_key, p.get(plan_key))
        if value is not None:
            result[key] = value
    for key in ('actual_start', 'actual_stop', 'iq_bytes', 'status', 'rtl_sdr_returncode'):
        if metadata.get(key) is not None:
            result[key] = metadata[key]
    if 'peak' not in result and p.get('peak') is not None:
        for key in ('peak', 'peak_deg', 'peak_azimuth', 'tle_epoch', 'tle_source'):
            if p.get(key) is not None:
                result[key] = p[key]
        result.setdefault('geometry_source', 'Retained managed plan')
    probe = metadata.get('iq_preflight')
    if isinstance(probe, dict):
        result['preflight'] = {key: probe.get(key) for key in ('success', 'attempt_count', 'byte_count')}
    return result


def capture_snapshot(metadata):
    """Called before preflight; never depends on network or decoder success."""
    import satellite_schedule as schedule
    c = json.loads((ROOT / 'meteor-config.json').read_text())
    tle_cache = json.loads((ROOT / 'data/meteor_tles.json').read_text())
    # Freeze inputs in memory so enrichment and retained elements use one version.
    result = recorded(metadata)
    result.update(satellite=metadata['satellite'], saved_at=datetime.now(timezone.utc).isoformat(),
                  observer={key:c[key] for key in ('latitude','longitude','observer_elevation_m')},
                  horizon_deg=c['horizon_deg'], timezone='Europe/Helsinki')
    warnings = []
    schedule.geometry([result], c, warnings, tle_cache=tle_cache)
    result['tle'] = tle_cache.get(metadata['satellite'])
    result['warnings'] = warnings
    result['geometry_source'] = 'Prediction saved before capture' if not warnings else 'Prediction unavailable at capture'
    return result
