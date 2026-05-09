#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ccsilo.downloader import download_binary
from ccsilo.patches import (
    Patch,
    PatchAnchorMissError,
    PatchBlacklistedError,
    PatchContext,
    PatchUnsupportedVersionError,
    apply_patches,
)
from ccsilo.patches._registry import REGISTRY

from tools.patch_release_check.bundle import extract_entry_js, file_sha256
from tools.patch_release_check.io import index_entry, print_result_summary, write_json, write_run_index
from tools.patch_release_check.models import (
    DEFAULT_CONFIG,
    DEFAULT_OVERLAYS,
    DEFAULT_REPORTS_DIR,
    DEFAULT_SMOKE_TIMEOUT_SECONDS,
    OUTPUT_LIMIT,
    SMOKE_ENV_DEFAULTS,
    PatchCheck,
    VersionReport,
)
from tools.patch_release_check.patches import patch_supported, patch_tested, smoke_patch_ids, summarize_checks
from tools.patch_release_check.smoke import _sanitize_output, run_binary_smoke, run_smoke_command, smoke_environment
from tools.patch_release_check.versions import (
    VERSION_RE,
    is_version,
    latest_report_version,
    missing_versions,
    newer_than,
    report_path,
    report_versions,
    resolve_versions,
    sort_versions,
    version_tuple,
    versions_since_existing_latest,
)

__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_OVERLAYS",
    "DEFAULT_REPORTS_DIR",
    "DEFAULT_SMOKE_TIMEOUT_SECONDS",
    "OUTPUT_LIMIT",
    "SMOKE_ENV_DEFAULTS",
    "VERSION_RE",
    "PatchCheck",
    "VersionReport",
    "_sanitize_output",
    "check_patch",
    "check_version",
    "extract_entry_js",
    "file_sha256",
    "index_entry",
    "is_version",
    "latest_report_version",
    "main",
    "missing_versions",
    "newer_than",
    "patch_supported",
    "patch_tested",
    "print_result_summary",
    "report_path",
    "report_versions",
    "resolve_versions",
    "run_binary_smoke",
    "run_smoke_command",
    "run_versions",
    "smoke_environment",
    "smoke_patch_ids",
    "sort_versions",
    "summarize_checks",
    "version_tuple",
    "versions_since_existing_latest",
    "write_json",
    "write_run_index",
]

def check_patch(
    js: str,
    patch: Patch,
    version: str,
    *,
    registry: Mapping[str, Patch],
    config: Optional[Mapping[str, Any]] = None,
    overlays: Optional[Mapping[str, str]] = None,
) -> PatchCheck:
    ctx = PatchContext(
        claude_version=version,
        provider_label="Patch compatibility",
        config=config or DEFAULT_CONFIG,
        overlays=overlays or DEFAULT_OVERLAYS,
    )
    caught_warnings: List[str] = []
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                result = apply_patches(js, [patch.id], ctx, registry=registry)
            finally:
                caught_warnings = [str(item.message) for item in caught]
    except PatchAnchorMissError as exc:
        return PatchCheck(
            patch.id,
            patch.name,
            patch.group,
            "missed",
            False,
            patch_supported(patch, version),
            patch_tested(patch, version),
            caught_warnings,
            [],
            str(exc),
        )
    except PatchUnsupportedVersionError as exc:
        return PatchCheck(
            patch.id,
            patch.name,
            patch.group,
            "unsupported",
            True,
            False,
            patch_tested(patch, version),
            caught_warnings,
            [],
            str(exc),
        )
    except PatchBlacklistedError as exc:
        return PatchCheck(
            patch.id,
            patch.name,
            patch.group,
            "blacklisted",
            True,
            patch_supported(patch, version),
            False,
            caught_warnings,
            [],
            str(exc),
        )
    except Exception as exc:
        return PatchCheck(
            patch.id,
            patch.name,
            patch.group,
            "error",
            False,
            patch_supported(patch, version),
            patch_tested(patch, version),
            caught_warnings,
            [],
            str(exc),
        )

    if result.applied:
        status = "applied"
        ok = True
    elif result.skipped:
        status = "skipped"
        ok = True
    elif result.missed:
        status = "missed"
        ok = False
    else:
        status = "no-op"
        ok = False
    return PatchCheck(
        patch.id,
        patch.name,
        patch.group,
        status,
        ok,
        patch_supported(patch, version),
        patch_tested(patch, version),
        caught_warnings,
        list(result.notes),
    )

def check_version(
    version: str,
    *,
    registry: Mapping[str, Patch] = REGISTRY,
    downloader=download_binary,
    run_smoke: bool = False,
    smoke_timeout: int = DEFAULT_SMOKE_TIMEOUT_SECONDS,
    smoke_runner=None,
) -> Dict[str, Any]:
    binary_path = Path(downloader(version=version))
    js, binary = extract_entry_js(binary_path)
    checks = [
        check_patch(js, patch, version, registry=registry)
        for patch in registry.values()
    ]
    summary = summarize_checks(checks)
    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "version": version,
        "binary": binary,
        "summary": summary,
        "ok": summary["failed"] == 0,
        "patches": [
            {
                "id": check.id,
                "name": check.name,
                "group": check.group,
                "status": check.status,
                "ok": check.ok,
                "supported": check.supported,
                "tested": check.tested,
                "warnings": check.warnings,
                "notes": check.notes,
                "detail": check.detail,
            }
            for check in checks
        ],
    }
    if run_smoke:
        runner = smoke_runner or run_binary_smoke
        smoke = runner(
            binary_path,
            version,
            registry=registry,
            timeout=smoke_timeout,
        )
        report["smoke"] = smoke
        if smoke.get("ok") is False:
            report["ok"] = False
    return report

def run_versions(args: argparse.Namespace) -> List[VersionReport]:
    versions = resolve_versions(args)
    if args.max_versions is not None:
        versions = versions[: args.max_versions]

    reports = []
    results = []
    for version in versions:
        print(f"[*] Checking patches against Claude Code {version}")
        output_path = report_path(args.reports_dir, version)
        try:
            report = check_version(
                version,
                run_smoke=args.run_smoke,
                smoke_timeout=args.smoke_timeout,
            )
            write_json(output_path, report)
            reports.append(report)
            results.append(
                VersionReport(
                    version=version,
                    ok=bool(report["ok"]),
                    output_path=output_path,
                    summary=dict(report["summary"]),
                    smoke=report.get("smoke"),
                )
            )
            print_result_summary(results[-1])
            if args.stop_on_error and not report["ok"]:
                break
        except Exception as exc:
            error_report = {
                "schemaVersion": 1,
                "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "version": version,
                "ok": False,
                "error": str(exc),
                "summary": {"total": 0, "ok": 0, "failed": 1, "untested": 0},
                "patches": [],
            }
            write_json(output_path, error_report)
            reports.append(error_report)
            result = VersionReport(
                version=version,
                ok=False,
                output_path=output_path,
                summary=dict(error_report["summary"]),
                error=str(exc),
            )
            results.append(result)
            print(f"[!] {version}: {exc}", file=sys.stderr)
            if args.stop_on_error:
                break

    if reports:
        write_run_index(args.reports_dir, reports)
    return results

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check curated regex patches against Claude Code releases"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--all", action="store_true", help="Process all available binary versions")
    source.add_argument("--latest", action="store_true", help="Process the latest binary version")
    source.add_argument("--versions", nargs="+", help="Specific versions to process")
    source.add_argument(
        "--missing",
        action="store_true",
        help="Process released versions missing from --reports-dir",
    )
    source.add_argument(
        "--since-existing-latest",
        action="store_true",
        help="Process released versions newer than the newest report JSON",
    )
    parser.add_argument("--max-versions", type=int, help="Limit processed version count")
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument(
        "--run-smoke",
        action="store_true",
        help="Build a temporary patched binary and run '<binary> --version'",
    )
    parser.add_argument(
        "--smoke-timeout",
        type=int,
        default=DEFAULT_SMOKE_TIMEOUT_SECONDS,
        help="Seconds to wait for each runtime smoke command",
    )
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args(argv)

    results = run_versions(args)
    failed = [result for result in results if not result.ok]
    print(f"[*] Complete: {len(results) - len(failed)} ok, {len(failed)} failed")
    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
