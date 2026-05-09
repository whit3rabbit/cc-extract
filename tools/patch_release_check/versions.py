"""Version and report selection helpers."""

import argparse
import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from ccsilo.downloader import fetch_latest_binary_version, list_available_binary_versions

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

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
