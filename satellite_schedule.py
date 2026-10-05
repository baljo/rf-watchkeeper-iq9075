"""Read-only dashboard view of managed passes and live capture timers."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent
UTC = timezone.utc


def dt(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Timezone required')
    return stamp.astimezone(UTC)


def command(*args):
    return subprocess.check_output(['systemctl', *args], text=True, timeout=5).strip()


def argument(text, flag, default=None):
    match = re.search(r'"?' + re.escape(flag) + r'"?\s+"?([^"\s]+)', text)
    return match.group(1) if match else default


def manual_row(unit, text):
    if 'satellite_capture.py' not in text:
        return None
    start, stop = argument(text, '--start'), argument(text, '--stop')
    satellite = argument(text, '--satellite')
    if not start or not stop or satellite not in ('M2-3', 'M2-4'):
        return None
    pre, post = int(argument(text, '--pre-margin', '90')), int(argument(text, '--post-margin', '90'))
    return dict(id=unit, satellite=satellite, start=dt(start).isoformat(), stop=dt(stop).isoformat(),
                record_start=(dt(start)-timedelta(seconds=pre)).isoformat(),
                record_stop=(dt(stop)+timedelta(seconds=post)).isoformat(),
                frequency=int(argument(text, '--frequency', '137900000')),
                sample_rate=int(argument(text, '--sample-rate', '1024000')),
                device=argument(text, '--device', 'V4MAIN01'), source='Capture timer', unit=unit)


def geometry(rows, config, warnings, tle_cache=None):
    # Use the planner's existing TLE cache only. No fetch, plan write or scheduling.
    try:
        import satellite_planner as planner
        cache = tle_cache if tle_cache is not None else json.loads((ROOT / 'data/meteor_tles.json').read_text())
        ts = planner.load.timescale(builtin=True)
        observer = planner.wgs84.latlon(config['latitude'], config['longitude'], elevation_m=config['observer_elevation_m'])
    except (OSError, ValueError, ImportError, KeyError) as error:
        warnings.append('Direction predictions unavailable: ' + str(error))
        return
    for row in rows:
        try:
            tle = cache[row['satellite']]
            sat = planner.EarthSatellite(tle['line1'], tle['line2'], tle['name'], ts)
            if sat.model.satnum != planner.SATELLITES[row['satellite']]['norad']:
                raise ValueError('Unexpected NORAD ID')
            if max(abs((dt(row[key])-sat.epoch.utc_datetime()).total_seconds()) for key in ('start', 'stop')) > config['max_tle_age_days']*86400:
                raise ValueError('Cached orbital elements are too old')
            row['start_azimuth'] = planner.angle_at(sat, observer, ts.from_datetime(dt(row['start'])))[1]
            row['end_azimuth'] = planner.angle_at(sat, observer, ts.from_datetime(dt(row['stop'])))[1]
            if not row.get('peak'):
                times, events = sat.find_events(observer, ts.from_datetime(dt(row['start'])), ts.from_datetime(dt(row['stop'])), altitude_degrees=0)
                peaks = [(t, planner.angle_at(sat, observer, t)) for t,e in zip(times,events) if e == 1]
                if peaks:
                    t, (alt, az) = max(peaks, key=lambda item:item[1][0])
                    row.update(peak=t.utc_datetime().isoformat(), peak_deg=alt, peak_azimuth=az)
            row['geometry_source'] = 'Cached TLE'
            row['tle_epoch'] = sat.epoch.utc_datetime().isoformat()
        except (ValueError, KeyError, OSError) as error:
            warnings.append(row['satellite'] + ': ' + str(error))


def snapshot():
    stamp = datetime.now(UTC)
    warnings, rows = [], []
    config = json.loads((ROOT / 'meteor-config.json').read_text())
    plan = {}
    try:
        plan = json.loads((ROOT / 'data/meteor-auto/plan.json').read_text())
    except (OSError, ValueError):
        warnings.append('Managed plan unavailable')
    dispatcher = command('show', 'rf-watchkeeper-meteor-dispatch.timer', '-p', 'ActiveState', '--value') == 'active'
    for p in plan.get('passes', []):
        if p.get('status') not in ('planned', 'claimed') or dt(p['record_stop']) <= stamp:
            continue
        row = dict(p, source='Managed planner')
        row['schedule_status'] = ('Claimed' if p['status']=='claimed' else
                                  'Paused' if not plan.get('enabled') or not dispatcher else
                                  'Overdue' if dt(p['trigger']) < stamp-timedelta(seconds=config['max_lateness_seconds']) else 'Scheduled')
        rows.append(row)
    try:
        names = command('list-units', '--all', '--type=timer', '--plain', '--no-legend').splitlines()
        for line in names:
            unit = line.split()[0]
            if not unit.startswith(('meteor-', 'satellite-')) or unit.startswith('meteor-auto-'):
                continue
            props = dict(line.split('=',1) for line in command('show', unit, '-p', 'ActiveState', '-p', 'NextElapseUSecRealtime').splitlines() if '=' in line)
            service = unit[:-6]+'.service'
            state = command('show', service, '-p', 'ActiveState', '--value')
            pending = props.get('ActiveState')=='active' and props.get('NextElapseUSecRealtime') not in (None,'','n/a')
            running = state in ('active','activating')
            if not pending and not running:
                continue
            row = manual_row(unit, command('cat', service))
            if row and dt(row['record_stop']) > stamp:
                row['schedule_status'] = 'Recording / preflight' if running else 'Scheduled'
                row['timer_next'] = props.get('NextElapseUSecRealtime')
                if pending:
                    row['trigger'] = datetime.strptime(row['timer_next'], '%a %Y-%m-%d %H:%M:%S %Z').replace(tzinfo=UTC).isoformat()
                rows.append(row)
    except (subprocess.SubprocessError, ValueError, OSError) as error:
        warnings.append('Capture timer status unavailable: '+str(error))
    geometry(rows, config, warnings)
    return dict(passes=sorted(rows,key=lambda p:dt(p['start'])), generated_at=plan.get('generated_at'),
                checked_at=stamp.isoformat(), timezone='Europe/Helsinki', horizon_deg=config['horizon_deg'],
                observer={k:config[k] for k in ('latitude','longitude','observer_elevation_m')},
                warnings=warnings)


if __name__ == '__main__':
    print(json.dumps(snapshot(), allow_nan=False))
