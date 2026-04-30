"""Shared low-level helpers used across the package.

Kept self-contained so it can be imported from any module without circular
risk: only stdlib imports allowed here.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

_KEBAB_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def safe_read_json(path: Path) -> Dict:
    """Read JSON from `path` returning `{}` on missing file or parse error."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def version_sort_key(version: Any) -> Tuple[int, int, int, int]:
    """Sort key for dotted version strings (best-effort, padded to 4 ints)."""
    parts = []
    for part in str(version).split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(-1)
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)


def utc_now() -> str:
    """ISO-8601 UTC timestamp with seconds resolution and `Z` suffix."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def make_kebab_id(name: str, *, label: str = "name") -> str:
    """Lower-kebab-case ID derived from a human-friendly `name`.

    Used for variant ids and patch profile ids; the produced slug is
    guaranteed to match `^[a-z0-9]+(?:-[a-z0-9]+)*$`.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{label} must be a non-empty string")
    slug = _KEBAB_NON_ALNUM.sub("-", name.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"{label} must contain letters or numbers")
    return slug
