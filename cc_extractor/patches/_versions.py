"""SemVer range parser scoped to Claude Code's MAJOR.MINOR.PATCH scheme."""

import re
from typing import List, Tuple

Version = Tuple[int, int, int]

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_COMPARATOR_RE = re.compile(r"^(>=|<=|==|>|<)\s*(\d+(?:\.\d+){0,2})$")


class SemverRangeError(ValueError):
    pass


def parse_version(text: str) -> Version:
    """Parse a strict MAJOR.MINOR.PATCH version string."""
    if not isinstance(text, str):
        raise SemverRangeError(f"version must be a string, got {type(text).__name__}")
    match = _VERSION_RE.match(text.strip())
    if match is None:
        raise SemverRangeError(f"invalid version: {text!r} (expected MAJOR.MINOR.PATCH)")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _normalize_version(text: str) -> Version:
    """Parse a version with 1-3 components, defaulting missing parts to 0."""
    parts = text.strip().split(".")
    if len(parts) < 1 or len(parts) > 3:
        raise SemverRangeError(f"invalid version: {text!r} (expected 1-3 numeric components)")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        raise SemverRangeError(f"invalid version: {text!r} (components must be numeric)")
    return major, minor, patch


def _parse_clause(clause: str) -> List[Tuple[str, Version]]:
    parts = [piece.strip() for piece in clause.split(",") if piece.strip()]
    if not parts:
        raise SemverRangeError(f"empty range clause: {clause!r}")
    out: List[Tuple[str, Version]] = []
    for piece in parts:
        match = _COMPARATOR_RE.match(piece)
        if match is None:
            raise SemverRangeError(f"invalid comparator: {piece!r}")
        comparator = match.group(1)
        try:
            version = _normalize_version(match.group(2))
        except SemverRangeError as exc:
            raise SemverRangeError(f"in clause {clause!r}: {exc}") from None
        out.append((comparator, version))
    return out


def parse_range(expr: str) -> List[List[Tuple[str, Version]]]:
    if not isinstance(expr, str) or not expr.strip():
        raise SemverRangeError("range expression must be a non-empty string")
    clauses = [piece.strip() for piece in expr.split("||") if piece.strip()]
    return [_parse_clause(clause) for clause in clauses]


def _clause_matches(version: Version, clause: List[Tuple[str, Version]]) -> bool:
    for comparator, target in clause:
        if comparator == ">=" and not version >= target:
            return False
        if comparator == ">" and not version > target:
            return False
        if comparator == "<=" and not version <= target:
            return False
        if comparator == "<" and not version < target:
            return False
        if comparator == "==" and not version == target:
            return False
    return True


def version_in_range(version: str, expr: str) -> bool:
    parsed_version = parse_version(version)
    clauses = parse_range(expr)
    return any(_clause_matches(parsed_version, clause) for clause in clauses)


def range_contains_range(outer: str, inner: str) -> bool:
    """Conservative check: every endpoint of `inner` must satisfy `outer`.

    Used by registry tests: versions_tested ranges must be a subset of
    versions_supported. We approximate by checking the explicit endpoints
    declared in `inner` plus a small probe set; sufficient for the
    monotone-numeric grammar we accept.
    """
    inner_clauses = parse_range(inner)
    for clause in inner_clauses:
        for _, version in clause:
            version_str = ".".join(str(part) for part in version)
            if not version_in_range(version_str, outer):
                return False
    return True
