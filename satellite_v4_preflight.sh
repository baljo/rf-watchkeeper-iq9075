#!/bin/sh
# Use the shared sample watchdog; preserve managed persistent reboot reservations.
if [ "$1" = "--reboot-only" ]; then
    /root/rf-watchkeeper/.satellite-venv/bin/python -c '
import json, sys
from pathlib import Path
sys.path.insert(0, "/root/rf-watchkeeper")
import meteor_recovery as recovery
p = Path(sys.argv[1]).resolve()
assert p.parent == recovery.STATE.resolve()
r = json.loads(p.read_text())
assert r["state"] == "reboot_requested" and r["reboot_count"] == 1
assert r["boot_id"] == recovery.boot_id()
' "$2" || exit 1
    sync
    systemctl reboot
    exit $?
fi
exec /usr/bin/python3 /root/rf-watchkeeper/rf_health_monitor.py --force-probe
