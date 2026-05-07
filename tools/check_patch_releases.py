#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ccsilo.bun_extract import parse_bun_binary
from ccsilo._utils import atomic_write_text_no_symlink
from ccsilo.bundler import pack_bundle
from ccsilo.binary_patcher.codesign import try_adhoc_sign
from ccsilo.downloader import (
    download_binary,
    fetch_latest_binary_version,
    get_platform_key,
    list_available_binary_versions,
)
from ccsilo.extractor import extract_all
from ccsilo.patch_workflow import _entry_path
from ccsilo.patches import (
    Patch,
    PatchAnchorMissError,
    PatchBlacklistedError,
    PatchContext,
    PatchUnsupportedVersionError,
    apply_patches,
)
from ccsilo.patches._registry import REGISTRY
from ccsilo.patches._versions import SemverRangeError, version_in_range


VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
DEFAULT_REPORTS_DIR = Path("reports") / "patch-compat"
DEFAULT_SMOKE_TIMEOUT_SECONDS = 60
OUTPUT_LIMIT = 4000
DEFAULT_CONFIG = {
    "settings": {
        "themes": [
            {"id": "compat-dark", "name": "Compat Dark", "colors": {"bashBorder": "#ffffff"}},
            {"id": "compat-provider", "name": "Compat Provider", "colors": {"bashBorder": "#dadada"}},
        ],
        "misc": {
            "tokenCountRounding": 1000,
            "statusLineUpdateThrottleMs": 300,
            "mcpServerConnectionBatchSize": 10,
        },
        "claudeMdAltNames": ["AGENTS.md", "CLAUDE.md"],
    },
}
DEFAULT_OVERLAYS = {"webfetch": "Patch compatibility smoke overlay."}
SMOKE_ENV_DEFAULTS = {
    "CI": "1",
    "NO_COLOR": "1",
    "DISABLE_TELEMETRY": "1",
    "DISABLE_ERROR_REPORTING": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1",
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
}


@dataclass
class PatchCheck:
    id: str
    name: str
    group: str
    status: str
    ok: bool
    supported: bool
    tested: bool
    warnings: List[str]
    notes: List[str]
    detail: str = ""


@dataclass
class VersionReport:
    version: str
    ok: bool
    output_path: Path
    summary: Dict[str, int]
    error: Optional[str] = None
    smoke: Optional[Dict[str, Any]] = None


def is_version(value: str) -> bool:
    return bool(VERSION_RE.match(value))


def version_tuple(version: str) -> Tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def newer_than(version: str, baseline: str) -> bool:
    return version_tuple(version) > version_tuple(baseline)


def sort_versions(versions: Iterable[str]) -> List[str]:
    return sorted(
        {version for version in versions if is_version(version)},
        key=version_tuple,
        reverse=True,
    )


def report_path(reports_dir: Path, version: str) -> Path:
    return reports_dir / f"{version}.json"


def report_versions(reports_dir: Path) -> List[str]:
    return sort_versions(path.stem for path in reports_dir.glob("*.json") if path.stem != "index")


def latest_report_version(reports_dir: Path) -> Optional[str]:
    versions = report_versions(reports_dir)
    return versions[0] if versions else None


def missing_versions(reports_dir: Path, available_versions: Sequence[str]) -> List[str]:
    existing = set(report_versions(reports_dir))
    return [
        version
        for version in sort_versions(available_versions)
        if version not in existing
    ]


def versions_since_existing_latest(
    reports_dir: Path,
    available_versions: Sequence[str],
) -> List[str]:
    latest_existing = latest_report_version(reports_dir)
    if latest_existing is None:
        return sort_versions(available_versions)
    return [
        version
        for version in sort_versions(available_versions)
        if newer_than(version, latest_existing)
    ]


def resolve_versions(args: argparse.Namespace) -> List[str]:
    if args.versions:
        return sort_versions(args.versions)
    if args.latest:
        return [fetch_latest_binary_version()]
    if args.missing:
        return missing_versions(args.reports_dir, list_available_binary_versions())
    if args.since_existing_latest:
        return versions_since_existing_latest(
            args.reports_dir,
            list_available_binary_versions(),
        )
    if args.all:
        return sort_versions(list_available_binary_versions())
    raise ValueError("Pass --versions, --latest, --missing, --since-existing-latest, or --all")


def extract_entry_js(binary_path: Path) -> Tuple[str, Dict[str, Any]]:
    data = binary_path.read_bytes()
    info = parse_bun_binary(data)
    if 0 <= info.entry_point_id < len(info.modules):
        module = info.modules[info.entry_point_id]
    else:
        module = next(
            (item for item in info.modules if item.name and item.name.endswith("cli.js")),
            None,
        )
        if module is None:
            raise RuntimeError(f"entry module not found inside {binary_path}")
    start = info.data_start + module.cont_off
    entry_bytes = data[start : start + module.cont_len]
    return entry_bytes.decode("utf-8", errors="replace"), {
        "entryModule": module.name,
        "entryBytes": len(entry_bytes),
    }


def file_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def patch_supported(patch: Patch, version: str) -> bool:
    try:
        return version_in_range(version, patch.versions_supported)
    except SemverRangeError:
        return False


def patch_tested(patch: Patch, version: str) -> bool:
    for tested_range in patch.versions_tested:
        try:
            if version_in_range(version, tested_range):
                return True
        except SemverRangeError:
            continue
    return False


def smoke_patch_ids(registry: Mapping[str, Patch], version: str) -> List[str]:
    return [
        patch.id
        for patch in registry.values()
        if patch_supported(patch, version)
    ]


def _sanitize_output(
    value: Optional[str],
    replacements: Sequence[Tuple[str, str]] = (),
) -> str:
    text = value or ""
    for old, new in replacements:
        if old:
            text = text.replace(old, new)
    if len(text) <= OUTPUT_LIMIT:
        return text
    return f"{text[:OUTPUT_LIMIT]}...<truncated>"


def smoke_environment(root: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    for key in ("PATH", "TMPDIR", "TEMP", "TMP", "SystemRoot", "WINDIR"):
        if key in os.environ:
            env[key] = os.environ[key]

    home = root / "home"
    config = root / "config"
    cache = root / "cache"
    data = root / "data"
    workspace = root / "workspace"
    for path in (home, config, cache, data, workspace):
        path.mkdir(parents=True, exist_ok=True)

    env.update(SMOKE_ENV_DEFAULTS)
    env.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(config),
            "XDG_CACHE_HOME": str(cache),
            "XDG_DATA_HOME": str(data),
            "CLAUDE_CONFIG_DIR": str(config / "claude"),
            "CLAUDE_CODE_CONFIG_DIR": str(config / "claude-code"),
            "CCSILO_WORKSPACE": str(workspace),
        }
    )
    return env


def run_smoke_command(
    binary_path: Path,
    temp_root: Path,
    *,
    timeout: int,
    label: str,
    replacements: Sequence[Tuple[str, str]],
    expected_version: Optional[str] = None,
) -> Dict[str, Any]:
    proc = subprocess.run(
        [str(binary_path), "--version"],
        env=smoke_environment(temp_root),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    stdout = _sanitize_output(proc.stdout, replacements)
    stderr = _sanitize_output(proc.stderr, replacements)
    version_matched = expected_version is None or expected_version in (proc.stdout or "")
    ok = proc.returncode == 0 and bool((proc.stdout or "").strip()) and version_matched
    return {
        "ok": ok,
        "command": [label, "--version"],
        "exitCode": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "expectedVersion": expected_version,
        "versionMatched": version_matched,
    }


def run_binary_smoke(
    binary_path: Path,
    version: str,
    *,
    registry: Mapping[str, Patch] = REGISTRY,
    timeout: int = DEFAULT_SMOKE_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    started = time.monotonic()
    stage = "prepare"
    replacements: List[Tuple[str, str]] = []
    patch_ids = smoke_patch_ids(registry, version)
    platform_key = get_platform_key()
    if not patch_ids:
        return {
            "ok": False,
            "status": "failed",
            "stage": stage,
            "platformKey": platform_key,
            "detail": "no supported patches selected for smoke",
            "durationMs": int((time.monotonic() - started) * 1000),
            "patchIds": [],
        }

    try:
        with tempfile.TemporaryDirectory(prefix=f"patch-smoke-{version}-") as temp_dir:
            temp_root = Path(temp_dir)
            extract_dir = temp_root / "bundle"
            baseline_binary = temp_root / f"baseline-{binary_path.name}"
            patched_binary = temp_root / binary_path.name
            replacements = [
                (str(baseline_binary), "<baseline-binary>"),
                (str(patched_binary), "<patched-binary>"),
                (str(temp_root), "<temp>"),
            ]

            stage = "extract"
            manifest_data = extract_all(
                str(binary_path),
                str(extract_dir),
                source_version=version,
            )
            entry_path = _entry_path(extract_dir, manifest_data)
            js = entry_path.read_text(encoding="utf-8")

            stage = "baseline-pack"
            pack_bundle(str(extract_dir), str(baseline_binary), str(binary_path))
            if os.name != "nt":
                os.chmod(baseline_binary, 0o755)

            stage = "baseline-codesign"
            baseline_sign_result = try_adhoc_sign(str(baseline_binary))
            baseline_sign_detail = _sanitize_output(baseline_sign_result.detail, replacements)
            if baseline_sign_result.reason == "failed":
                return {
                    "ok": None,
                    "status": "blocked",
                    "stage": stage,
                    "platformKey": platform_key,
                    "detail": baseline_sign_detail,
                    "durationMs": int((time.monotonic() - started) * 1000),
                    "outputSha256": file_sha256(baseline_binary),
                    "codesign": {
                        "signed": baseline_sign_result.signed,
                        "reason": baseline_sign_result.reason,
                        "detail": baseline_sign_detail,
                    },
                    "patchIds": patch_ids,
                }

            stage = "baseline-run"
            baseline = run_smoke_command(
                baseline_binary,
                temp_root,
                timeout=timeout,
                label="<baseline-binary>",
                replacements=replacements,
                expected_version=version,
            )
            if not baseline["ok"]:
                return {
                    "ok": None,
                    "status": "blocked",
                    "stage": stage,
                    "platformKey": platform_key,
                    "detail": "unpatched repack failed before patch smoke",
                    "baseline": baseline,
                    "durationMs": int((time.monotonic() - started) * 1000),
                    "outputSha256": file_sha256(baseline_binary),
                    "codesign": {
                        "signed": baseline_sign_result.signed,
                        "reason": baseline_sign_result.reason,
                        "detail": baseline_sign_detail,
                    },
                    "patchIds": patch_ids,
                }

            stage = "patch"
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                patch_result = apply_patches(
                    js,
                    patch_ids,
                    PatchContext(
                        claude_version=version,
                        provider_label="Patch compatibility smoke",
                        config=DEFAULT_CONFIG,
                        overlays=DEFAULT_OVERLAYS,
                    ),
                    registry=registry,
                )
            atomic_write_text_no_symlink(entry_path, patch_result.js)

            stage = "pack"
            pack_bundle(str(extract_dir), str(patched_binary), str(binary_path))
            if os.name != "nt":
                os.chmod(patched_binary, 0o755)

            stage = "codesign"
            sign_result = try_adhoc_sign(str(patched_binary))
            sign_detail = _sanitize_output(sign_result.detail, replacements)
            if sign_result.reason == "failed":
                return {
                    "ok": None,
                    "status": "blocked",
                    "stage": stage,
                    "platformKey": platform_key,
                    "detail": sign_detail,
                    "durationMs": int((time.monotonic() - started) * 1000),
                    "outputSha256": file_sha256(patched_binary),
                    "codesign": {
                        "signed": sign_result.signed,
                        "reason": sign_result.reason,
                        "detail": sign_detail,
                    },
                    "patches": {
                        "attempted": patch_ids,
                        "applied": list(patch_result.applied),
                        "skipped": list(patch_result.skipped),
                        "missed": list(patch_result.missed),
                        "warnings": [str(item.message) for item in caught],
                    },
                }

            stage = "run"
            run_result = run_smoke_command(
                patched_binary,
                temp_root,
                timeout=timeout,
                label="<patched-binary>",
                replacements=replacements,
                expected_version=version,
            )
            ok = bool(run_result["ok"])
            return {
                "ok": ok,
                "status": "passed" if ok else "failed",
                "stage": stage,
                "platformKey": platform_key,
                **run_result,
                "durationMs": int((time.monotonic() - started) * 1000),
                "outputSha256": file_sha256(patched_binary),
                "codesign": {
                    "signed": sign_result.signed,
                    "reason": sign_result.reason,
                    "detail": sign_detail,
                },
                "baselineCodesign": {
                    "signed": baseline_sign_result.signed,
                    "reason": baseline_sign_result.reason,
                    "detail": baseline_sign_detail,
                },
                "patches": {
                    "attempted": patch_ids,
                    "applied": list(patch_result.applied),
                    "skipped": list(patch_result.skipped),
                    "missed": list(patch_result.missed),
                    "warnings": [str(item.message) for item in caught],
                },
            }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "status": "timeout",
            "stage": stage,
            "platformKey": platform_key,
            "command": ["<patched-binary>", "--version"],
            "timeoutSeconds": timeout,
            "stdout": _sanitize_output(
                exc.stdout if isinstance(exc.stdout, str) else "",
                replacements,
            ),
            "stderr": _sanitize_output(
                exc.stderr if isinstance(exc.stderr, str) else "",
                replacements,
            ),
            "durationMs": int((time.monotonic() - started) * 1000),
            "patchIds": patch_ids,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "error",
            "stage": stage,
            "platformKey": platform_key,
            "detail": _sanitize_output(str(exc), replacements),
            "durationMs": int((time.monotonic() - started) * 1000),
            "patchIds": patch_ids,
        }


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


def summarize_checks(checks: Sequence[PatchCheck]) -> Dict[str, int]:
    summary = {
        "total": len(checks),
        "ok": sum(1 for check in checks if check.ok),
        "failed": sum(1 for check in checks if not check.ok),
        "untested": sum(1 for check in checks if not check.tested),
    }
    for check in checks:
        summary[check.status] = summary.get(check.status, 0) + 1
    return summary


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
