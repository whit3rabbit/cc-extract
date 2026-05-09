"""Report writing and CLI output helpers."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from .models import VersionReport

def write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def write_run_index(reports_dir: Path, reports: Sequence[Dict[str, Any]]) -> None:
    payload = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "reports": [index_entry(report) for report in reports],
    }
    write_json(reports_dir / "index.json", payload)

def index_entry(report: Mapping[str, Any]) -> Dict[str, Any]:
    entry = {
        "version": report["version"],
        "ok": report["ok"],
        "summary": report["summary"],
        "path": f"{report['version']}.json",
    }
    smoke = report.get("smoke")
    if isinstance(smoke, Mapping):
        entry["smoke"] = {
            "ok": smoke.get("ok"),
            "status": smoke.get("status"),
            "stage": smoke.get("stage"),
            "platformKey": smoke.get("platformKey"),
        }
    return entry

def print_result_summary(result: VersionReport) -> None:
    summary = result.summary
    status = "ok" if result.ok else "failed"
    smoke = ""
    if result.smoke:
        smoke = f", smoke {result.smoke.get('status', 'unknown')}"
    print(
        f"[+] {result.version}: {status}, "
        f"{summary.get('ok', 0)}/{summary.get('total', 0)} patches ok, "
        f"{summary.get('untested', 0)} untested{smoke} -> {result.output_path}"
    )
