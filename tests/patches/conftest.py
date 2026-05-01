"""Shared fixtures and helpers for patch tests."""

from typing import List

from cc_extractor.download_index import load_download_index
from cc_extractor.patches._versions import resolve_range_to_version


def resolve_tested_versions(patch) -> List[str]:
    """Resolve every range in patch.versions_tested to its highest concrete
    version in the local download index. Returns deduplicated list. Ranges
    that resolve to None are dropped (parametrize will skip those buckets
    via pytest.skip in the test body if needed)."""
    index = load_download_index()
    out: List[str] = []
    for range_expr in patch.versions_tested:
        version = resolve_range_to_version(range_expr, index=index)
        if version is not None and version not in out:
            out.append(version)
    return out
