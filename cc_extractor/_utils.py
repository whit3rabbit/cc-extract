"""Shared low-level helpers used across the package.

Kept self-contained so it can be imported from any module without circular
risk: only stdlib imports allowed here.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, Tuple

_KEBAB_NON_ALNUM = re.compile(r"[^a-z0-9]+")
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def safe_read_json(path: Path) -> Dict:
    """Read JSON from `path` returning `{}` on missing file or parse error."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def atomic_write_text_no_symlink(
    path: Path,
    text: str,
    *,
    mode: int = 0o644,
    encoding: str = "utf-8",
) -> None:
    """Atomically write text without following an existing target symlink."""
    atomic_write_bytes_no_symlink(path, text.encode(encoding), mode=mode)


def atomic_write_bytes_no_symlink(path: Path, data: bytes, *, mode: int = 0o644) -> None:
    """Atomically write bytes without following an existing target symlink."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Refusing to overwrite symlink: {path}")

    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    fd = os.open(tmp, flags, mode)
    replaced = False
    try:
        if os.name != "nt" and hasattr(os, "fchmod"):
            os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        replaced = True
        _fsync_directory(path.parent)
    finally:
        if fd is not None:
            os.close(fd)
        if not replaced:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


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


def require_env_name(name: str, *, label: str = "environment variable") -> str:
    """Return a shell-safe environment variable name or raise ValueError."""
    if not isinstance(name, str) or not ENV_NAME_RE.fullmatch(name):
        raise ValueError(f"{label} must match [A-Za-z_][A-Za-z0-9_]*")
    return name


def safe_relative_path(rel_path: str, *, label: str = "path") -> str:
    """Validate a bundle/package relative path and return slash-normalized text."""
    if not isinstance(rel_path, str) or not rel_path:
        raise ValueError(f"{label} must be a non-empty relative path")

    normalized = rel_path.replace("\\", "/")
    windows_path = PureWindowsPath(rel_path)
    if (
        PurePosixPath(normalized).is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or normalized.startswith("//")
        or ":" in normalized
    ):
        raise ValueError(f"{label} must be a relative path: {rel_path}")

    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{label} contains unsafe path segment: {rel_path}")
    if os.name == "nt" and any(_is_windows_reserved_name(part) for part in parts):
        raise ValueError(f"{label} contains a Windows reserved name: {rel_path}")
    return "/".join(parts)


def safe_child_path(root: Path, rel_path: str, *, label: str = "path") -> Path:
    """Resolve a safe child path under root, rejecting traversal and symlink escapes."""
    normalized = safe_relative_path(rel_path, label=label)
    root_resolved = Path(root).resolve()
    candidate = (root_resolved / Path(*normalized.split("/"))).resolve()
    if candidate == root_resolved or root_resolved not in candidate.parents:
        raise ValueError(f"{label} escapes root: {rel_path}")
    return candidate


def _is_windows_reserved_name(segment: str) -> bool:
    base = segment.split(".", 1)[0].upper()
    return base in _WINDOWS_RESERVED_NAMES
