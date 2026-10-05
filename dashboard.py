# Serve RF, AIS and historical METEOR imagery through explicit controlled image routes; 2026-10-03 EEST, Thomas Vikström.
"""Standard-library LAN dashboard with one saved-audio job at a time."""
import argparse
from datetime import datetime, timezone
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from audio_workflow import AudioWorkflow
import rf_store
import rf_health
import atis_view
import ais_store
import meteor_store
import meteor_retention
import sqlite3
import subprocess
import threading
import time
from ais_display import enrich_met_hydro

ROOT = Path(__file__).resolve().parent

_schedule_lock = threading.Lock()
_schedule_cache = None
_schedule_checked = 0


def satellite_schedule():
    global _schedule_cache, _schedule_checked
    with _schedule_lock:
        if _schedule_cache is not None and time.monotonic() - _schedule_checked < 30:
            return _schedule_cache
        result = subprocess.run([str(ROOT / '.satellite-venv/bin/python'),
                                 str(ROOT / 'satellite_schedule.py')],
                                capture_output=True, text=True, timeout=20, check=True)
        data = json.loads(result.stdout)
        _schedule_cache, _schedule_checked = data, time.monotonic()
        return data


def age_seconds(timestamp):
    try:
        stamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        return max(0, (datetime.now(timezone.utc) - stamp).total_seconds())
    except (ValueError, TypeError, AttributeError):
        return None


def receiver_status(status_path, label, device):
    """Return one normalized receiver status without coupling it to event storage."""
    receiver = {
        "label": label,
        "device": device,
        "state": "unknown",
        "job": None,
        "frequency_hz": None,
        "heartbeat_age_seconds": None,
        "detail": "No receiver heartbeat.",
    }
    if status_path is None:
        return receiver
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if not isinstance(status, dict):
            raise ValueError("Invalid status")
        age = age_seconds(status.get("updated_at"))
        state = status.get("state")
        valid = ("running", "starting", "stopped", "failed", "waiting",
                 "completed", "cancelled", "skipped")
        if state not in valid or age is None:
            raise ValueError("Invalid status")
        if state in ("running", "starting", "waiting", "completed",
                     "cancelled", "skipped") and age > 10:
            state = "unresponsive"
        receiver.update({
            "state": state,
            "job": status.get("job"),
            "mode": status.get("mode", "live"),
            "owner": status.get("owner", "scheduler"),
            "job_id": status.get("job_id"),
            "cycle": status.get("cycle"),
            "frequency_hz": status.get("frequency_hz"),
            "heartbeat_age_seconds": age,
            "detail": (
                "Receiver job active; this does not guarantee RF reception."
                if state == "running"
                else "Receiver is not currently confirmed running."
            ),
        })
    except (OSError, ValueError):
        pass
    return receiver


def read_events(path, allowed_sources=("live", "simulation", "replay")):
    """Read a bounded tail; ignore incomplete writes and non-normalized records."""
    try:
        with path.open("rb") as source:
            source.seek(0, 2)
            offset = max(0, source.tell() - 1024 * 1024)
            source.seek(offset)
            if offset:
                source.readline()  # discard possible partial leading record
            data = source.read(1024 * 1024)
    except FileNotFoundError:
        return [], "Waiting for the normalized event log"
    except OSError as error:
        return [], "Cannot read event log: " + str(error)
    events = []
    for line in data.split(b"\n")[:-1]:
        try:
            event = json.loads(line)
            json.dumps(event, allow_nan=False)
            if (isinstance(event, dict) and event.get("schema_version") == 1
                    and isinstance(event.get("event_type"), str)
                    and event.get("source") in allowed_sources
                    and age_seconds(event.get("received_at")) is not None):
                if atis_view.legacy_tiny(event):
                    event = dict(event)
                    event["text"] = "Unreliable legacy ATIS replay; use the Scheduled ATIS panel."
                    event["summary"] = "No usable ATIS interpretation: this used the old tiny-model replay."
                    event["quality_status"] = "unreliable_atis_tiny"
                # Explicit public fields: raw decoder payload is not consumed.
                events.append({key: event.get(key) for key in (
                    "schema_version", "event_type", "received_at", "source", "model",
                    "device_key", "sensor_id", "channel", "frequency_hz",
                    "temperature_c", "humidity_pct", "battery_ok", "state", "mode",
                    "job_id", "job", "processing_mode", "dwell_seconds", "reason", "cycle",
                    "text", "language", "language_requested", "model", "backend",
                    "processing_seconds", "audio_seconds", "accelerator_verified",
                    "accelerator_requested", "acceleration_note", "summary", "interpreter",
                    "input_event_type", "backend_error", "quality_status",
                   "mmsi", "message_type", "latitude", "longitude",
                   "distance_km", "bearing_deg", "bearing_text",
                   "vessel_name", "callsign", "speed_knots",
                   "course_deg", "heading_deg")})
        except (ValueError, UnicodeError):
            continue
    return events, None


def snapshot(log_path, status_path, transcription_path=None, db_path=rf_store.DEFAULT_DB, sensor_status_path=None):
    events, warning = read_events(log_path, ("live", "simulation"))
    transcriptions, transcription_warning = read_events(transcription_path, ("replay", "interpretation")) if transcription_path else ([], None)
    events = events + [event for event in transcriptions if event.get("event_type") in ("transcription", "interpretation")]
    events.sort(key=lambda event: event.get("received_at") or "")
    collector = receiver_status(
        status_path, "RTL-SDR Blog V4", "V4MAIN01"
    )
    sensor_receiver = receiver_status(
        sensor_status_path, "RTL2838 / FC0012", "43300001"
    )

    try:
        current_ais_status = json.loads(
            (ROOT / "logs" / "ais-status.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, json.JSONDecodeError):
        current_ais_status = {}

    ais_age = age_seconds(current_ais_status.get("updated_at"))
    if (
        current_ais_status.get("state") == "running"
        and ais_age is not None
        and ais_age <= 10
    ):
        collector.update({
            "state": "running",
            "job": "AIS reception",
            "job_id": "ais",
            "owner": "ais",
            "mode": "live",
            "frequency_hz": None,
            "heartbeat_age_seconds": ais_age,
            "detail": "AIS-catcher owns V4MAIN01 · dual-channel 161.975 / 162.025 MHz",
        })
    try:
        nexus_history = rf_store.nexus_history(1000, db_path)
        nexus_warning = None
    except Exception as error:
        # Keep the dashboard useful even if SQLite is temporarily unavailable.
        nexus_history = [
            e for e in events
            if e["model"] == "Nexus-TH"
            and e["event_type"] == "sensor_reading"
            and e["source"] == "live"
        ][-1000:]
        nexus_warning = "SQLite Nexus history unavailable: " + str(error)

    try:
        ais_targets = ais_store.recent_targets(50, db_path)
        ais_met_hydro = ais_store.recent_met_hydro(50, db_path)
        ais_met_hydro = enrich_met_hydro(ais_met_hydro, ROOT / "logs" / "ais-type8-raw.jsonl")
        ais_warning = None
    except Exception as error:
        ais_targets = []
        ais_met_hydro = []
        ais_warning = "SQLite AIS history unavailable: " + str(error)

    try:
        ais_status = json.loads(
            (ROOT / "logs" / "ais-status.json").read_text(encoding="utf-8")
        )
        if not isinstance(ais_status, dict):
            raise ValueError("Invalid AIS status")
    except (OSError, ValueError):
        ais_status = {
            "state": "unknown",
            "messages": 0,
            "unique_mmsi": 0,
            "observer_configured": False,
            "updated_at": None,
            "error": None,
        }

    try:
        receiver_health = rf_health.snapshot(db_path)
        satellite_health = next((r for r in receiver_health if r['serial']=='V4MAIN01'
                                 and r['status']=='BUSY' and 'satellite' in r.get('detail','').lower()), None)
        if satellite_health:
            collector.update(state='running',job='METEOR capture / preflight',owner='satellite',mode='live',
                             detail='Receiver reserved by active satellite capture; ordinary RF jobs paused',
                             frequency_hz=137900000)
            ais_status.update(state='paused',error=None)
        disabled = next((r for r in receiver_health if r["serial"] == "43300001" and r["status"] == "DISABLED"), None)
        if disabled:
            sensor_receiver.update(state="disabled", detail="Intentionally disconnected", job=None)
    except Exception as error:
        receiver_health = [{"serial":"V4MAIN01", "status":"UNKNOWN", "detail":"Health data unavailable: "+str(error)}]
    latest = nexus_history[-1] if nexus_history else None
    latest_transcription = next((e for e in reversed(events) if e["event_type"] == "transcription"), None)
    latest_interpretation = next((e for e in reversed(events) if e["event_type"] == "interpretation"), None)
    return {"rf_health": receiver_health, "api_version": 1, "server_time": datetime.now(timezone.utc).isoformat(),
            "dashboard": "online", "collector": collector, "sensor_receiver": sensor_receiver, "latest_nexus": latest,
            "latest_transcription": latest_transcription,
            "latest_interpretation": latest_interpretation,
            "latest_age_seconds": age_seconds(latest["received_at"]) if latest else None,
            "recent_events": list(reversed(events[-50:])),
            "warning": "; ".join(item for item in (warning, nexus_warning, ais_warning) if item) or None,
            "nexus_history": nexus_history,
          "ais_status": ais_status,
          "ais_targets": ais_targets,
          "ais_met_hydro": ais_met_hydro,
            "capabilities": {"controls": False, "airband": False, "ais": True,
                             "satellites": True, "utilization": False}}


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, log_path, status_path, transcription_path=None, db_path=rf_store.DEFAULT_DB, sensor_status_path=None, workflow=None, control_token=None, **kwargs):
        self.log_path, self.status_path, self.transcription_path = log_path, status_path, transcription_path
        self.db_path = db_path
        self.sensor_status_path = sensor_status_path
        self.workflow, self.control_token = workflow, control_token
        super().__init__(*args, **kwargs)

    def respond(self, data, content_type="application/json; charset=utf-8", status=200):
        if not isinstance(data, bytes):
            data = json.dumps(data, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        if urlsplit(self.path).path == '/api/meteor/pin':
            if not self.control_token or not secrets.compare_digest(self.headers.get('X-Watchkeeper-Token', ''), self.control_token):
                return self.respond({'error': 'Refresh the dashboard before changing Keep protection.'}, status=403)
            try:
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    return self.respond({'error': 'Expected JSON'}, status=415)
                self.connection.settimeout(5)
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    raise ValueError('Invalid request length')
                request = json.loads(self.rfile.read(length))
                if type(request.get('keep')) is not bool:
                    raise ValueError('Boolean keep is required')
                c = json.loads((ROOT / 'meteor-config.json').read_text())
                return self.respond(meteor_retention.pin(ROOT, c, request.get('id', ''), request['keep']))
            except BlockingIOError:
                return self.respond({'error': 'Satellite operation active; retry shortly.'}, status=409)
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
                return self.respond({'error': str(exc)}, status=400)
        if urlsplit(self.path).path != "/api/audio/run" or not self.workflow:
            return self.respond({"error": "Unknown route"}, status=404)
        if not self.control_token or not secrets.compare_digest(self.headers.get("X-Watchkeeper-Token", ""), self.control_token):
            return self.respond({"error": "Refresh the dashboard before starting a run."}, status=403)
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.respond({"error": "Expected JSON"}, status=415)
        self.connection.settimeout(5)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("Invalid request length")
            request = json.loads(self.rfile.read(length))
            if not isinstance(request, dict) or not isinstance(request.get("recording_id"), str) or not isinstance(request.get("language"), str):
                raise ValueError("Choose a recording and language")
            state = self.workflow.start(request["recording_id"], request["language"])
            self.respond(state, status=202)
        except (OSError, ValueError) as exc:
            self.respond({"error": str(exc)}, status=400)
        except RuntimeError as exc:
            self.respond({"error": str(exc)}, status=409)

    def do_GET(self):
        route = urlsplit(self.path).path
        if route == "/api/meteor/schedule":
            try:
                return self.respond(satellite_schedule())
            except (OSError, ValueError, subprocess.SubprocessError):
                return self.respond({'error': 'Satellite schedule temporarily unavailable'}, status=503)
        if route == "/api/meteor":
            try:
                c = json.loads((ROOT / 'meteor-config.json').read_text())
                data = meteor_retention.dashboard(ROOT, c, meteor_store.history())
                data['control_token'] = self.control_token
                return self.respond(data)
            except (OSError, ValueError, sqlite3.Error):
                return self.respond({'error':'Satellite history temporarily unavailable'}, status=503)
        if route.startswith("/api/meteor/image/"):
            try:
                path = meteor_store.image_file(route[len('/api/meteor/image/'):])
                return self.respond(path.read_bytes(), "image/png")
            except (OSError, ValueError, sqlite3.Error):
                return self.respond({'error':'Satellite image unavailable'}, status=404)
        if route == "/api/tower":
            try:
                return self.respond(atis_view.snapshot(ROOT, 'tower'))
            except (OSError, ValueError) as error:
                return self.respond({'status':'unavailable','message':str(error)}, status=503)
        if route == "/api/tower/audio":
            try:
                return self.respond(atis_view.audio(ROOT, 'tower'), "audio/wav")
            except (OSError, ValueError):
                return self.respond({'error':'Tower audio unavailable'}, status=404)
        if route == "/api/atis":
            try:
                return self.respond(atis_view.snapshot(ROOT))
            except (OSError, ValueError):
                return self.respond({"status":"unavailable","message":"ATIS results unavailable; retry shortly."}, status=503)
        if route == "/api/atis/audio":
            try:
                return self.respond(atis_view.audio(ROOT), "audio/wav")
            except (OSError, ValueError):
                return self.respond({"error":"ATIS audio unavailable"}, status=404)
        if route == "/api/nexus/history":
            query = parse_qs(urlsplit(self.path).query)
            try:
                return self.respond(rf_store.nexus_chart_history(
                    query.get("period", ["24"])[0], query.get("sensor", [None])[0], self.db_path))
            except ValueError as error:
                return self.respond({"error": str(error)}, status=400)
            except Exception:
                return self.respond({"error": "SQLite Nexus history unavailable; retrying shortly."}, status=503)
        if route == "/api/audio" and self.workflow:
            return self.respond({"recordings": list(self.workflow.catalog().values()), "run": self.workflow.snapshot(), "control_token": self.control_token})
        elif route.startswith("/api/audio/file/") and self.workflow:
            try:
                path, _ = self.workflow.recording(route[len("/api/audio/file/"):])
                # Eligible clips are <=30 seconds, mono PCM16/16 kHz. Bound extra WAV metadata too.
                with path.open("rb") as stream:
                    data = stream.read(2 * 1024 * 1024 + 1)
                if len(data) > 2 * 1024 * 1024:
                    raise ValueError("WAV exceeds playback size limit")
                return self.respond(data, "audio/wav")
            except (OSError, ValueError):
                return self.respond({"error": "Recording unavailable"}, status=404)
        elif route == "/api/state":
            data = json.dumps(
            snapshot(
                self.log_path,
                self.status_path,
                self.transcription_path,
                self.db_path,
                sensor_status_path=self.sensor_status_path,
            ),
            allow_nan=False,
        ).encode()
            content_type = "application/json; charset=utf-8"
        elif route == "/static/map/kvarken_land.geojson":
            data = (ROOT / "static" / "map" / "kvarken_land.geojson").read_bytes()
            content_type = "application/geo+json; charset=utf-8"
        elif route in ("/", "/index.html"):
            data = (ROOT / "dashboard.html").read_bytes()
            content_type = "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.respond(data, content_type)

    def log_message(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--log", type=Path, default=ROOT / "logs/events.jsonl")
    parser.add_argument("--db", type=Path, default=rf_store.DEFAULT_DB)
    parser.add_argument("--status", type=Path, help="Defaults to status.json beside event log")
    parser.add_argument("--sensor-status", type=Path, default=ROOT / "sensor-logs/status.json",
                        help="Dedicated FC0012 scheduler status")
    parser.add_argument("--transcription-log", type=Path,
                        help="Optional normalized ASR JSONL log; default: asr-events.jsonl beside event log")
    parser.add_argument("--genie-config", type=Path, default=Path("/root/genie/qwen3-4b-iq9075/genie_config.absolute.json"))
    args = parser.parse_args()
    transcription_log = args.transcription_log or args.log.with_name("asr-events.jsonl")
    workflow = AudioWorkflow(ROOT, transcription_log, args.genie_config)
    handler = partial(
        Handler,
        log_path=args.log,
        status_path=args.status or args.log.with_name("status.json"),
        transcription_path=transcription_log,
        db_path=args.db,
        sensor_status_path=args.sensor_status,
        workflow=workflow,
        control_token=secrets.token_hex(32),
    )
    with ThreadingHTTPServer((args.host, args.port), handler) as server:
        print("RF Watchkeeper dashboard listening on {}:{}".format(args.host, args.port), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
