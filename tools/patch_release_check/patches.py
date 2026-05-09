"""Patch status helpers for release compatibility checks."""

from typing import Dict, List, Mapping, Sequence

from ccsilo.patches import Patch
from ccsilo.patches._versions import SemverRangeError, version_in_range

from .models import PatchCheck

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
