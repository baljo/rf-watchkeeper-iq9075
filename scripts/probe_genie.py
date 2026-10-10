# Inventory Qualcomm Genie text-generation tools and local model/config assets without changing the EVK. 2026-09-17 20:40 EEST — Thomas Vikström.
"""Read-only Genie capability and model inventory for the RF Watchkeeper EVK."""

from __future__ import annotations

import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOTS = ("/root", "/usr/share", "/usr/lib", "/data", "/opt")
TOOLS = (
    "genie-t2t-run",
    "genie-t2e-run",
    "genie-app",
    "standalone-genie-vlm-test",
)
NAME_MARKERS = ("genie", "llm", "model", "config", "tokenizer", "qnn")


def run_help(tool: str) -> dict[str, object]:
    path = subprocess.run(
        ["sh", "-lc", f"command -v {tool}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if not path:
        return {"tool": tool, "path": None, "exit_code": None, "help": "missing"}
    result = subprocess.run(
        [path, "--help"], capture_output=True, text=True, check=False, timeout=15
    )
    text = (result.stdout + result.stderr).strip()
    return {
        "tool": tool,
        "path": path,
        "exit_code": result.returncode,
        "help": text[:12000],
    }


def inventory_paths() -> list[str]:
    found: list[str] = []
    for root in ROOTS:
        if not os.path.exists(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            depth = Path(dirpath).relative_to(root).parts
            if len(depth) > 5:
                dirnames[:] = []
                continue
            for name in (*dirnames, *filenames):
                lower = name.lower()
                if any(marker in lower for marker in NAME_MARKERS) and (
                    any(ext in lower for ext in (".bin", ".dlc", ".json", ".yaml", ".yml", ".cfg", ".so"))
                    or "genie" in lower
                    or "llm" in lower
                ):
                    found.append(os.path.join(dirpath, name))
                    if len(found) >= 500:
                        return sorted(set(found))
    return sorted(set(found))


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path("/root/rf-watchkeeper/genie-probes") / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "architecture": platform.machine(),
        "tools": [run_help(tool) for tool in TOOLS],
        "candidate_assets": inventory_paths(),
        "inference_run": False,
        "configuration_changed": False,
    }
    report_path = out_dir / "genie-inventory.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Genie inventory: {report_path}")
    for item in report["tools"]:
        print(f"TOOL {item['tool']}: {item['path'] or 'missing'}")
        if item["path"]:
            print(str(item["help"])[:1600])
    print(f"CANDIDATE_ASSETS {len(report['candidate_assets'])}")
    for path in report["candidate_assets"][:80]:
        print(path)
    print("No inference was run and no configuration was changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
