# Patches framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tested, version-aware patch framework under `cc_extractor/patches/`, migrate the 11 existing tweaks from `cc_extractor/variants/tweaks.py` into per-file modules behind a backwards-compatible shim, and ship a tiered test harness (L1 anchor / L2 JS-parses / L3 boot smoke / L4 TUI MCP behavioral).

**Architecture:** Each patch becomes a per-file module exposing a `Patch` dataclass with version metadata. The new `cc_extractor.patches.apply_patches` runs pre-flight version checks, calls `patch.apply`, and aggregates results. `variants/tweaks.py` shrinks to a ~50-line shim so existing callers and tests stay green. Tests are tiered: L1+L2 run under default `pytest`, L3+L4 are gated by env vars.

**Tech Stack:** Python 3.8+, pytest, stdlib `re`/`urllib`, optional Node (for L2 `node --check`), TUI MCP (for L4).

**Spec:** `docs/superpowers/specs/2026-04-30-patches-framework-design.md`

---

## File Structure

**New under `cc_extractor/patches/`:**
- `__init__.py` — `Patch`, `PatchContext`, `PatchOutcome`, `AggregateResult`, exceptions, `apply_patches`
- `_registry.py` — explicit `REGISTRY: dict[str, Patch]`, `get_patch(id)`, `registered_ids()`
- `_versions.py` — SemVer range parser, `version_in_range`, `resolve_range_to_version`
- `_helpers.py` — shared regex utilities (kept minimal until needed)
- `hide_startup_banner.py`
- `show_more_items.py`
- `model_customizations.py`
- `hide_startup_clawd.py`
- `hide_ctrl_g.py`
- `suppress_line_numbers.py`
- `auto_accept_plan_mode.py`
- `allow_custom_agent_models.py`
- `patches_applied_indication.py`
- `themes.py`
- `prompt_overlays.py`

**Modified:**
- `cc_extractor/variants/tweaks.py` — shim delegating to `cc_extractor.patches.apply_patches`
- `cc_extractor/patches/__init__.py` — already has `PatchResult`/helpers; new symbols added alongside

**New under `tests/patches/`:**
- `conftest.py` — `cli_js_real`, `cli_js_synthetic`, `parse_js`, `resolve_tested_versions`
- `_pinned.py` — `DEFAULT_VERSION_RANGES`
- `fixtures/synthetic.py` — handcrafted JS snippets, one per patch
- `test_registry.py` — cross-patch invariants
- `test_versions.py` — SemVer parser unit tests
- `test_<patch_id>.py` — per-patch L1 + L2 tests

**New under `tests/patches_smoke/`:** `test_variant_smoke.py` (L3, gated)

**New under `tests/patches_behavioral/`:** `conftest.py`, `test_<patch_id>.py`, `snapshots/<patch_id>.txt` (L4, gated)

**Docs:** `docs/patches.md` — patch authoring guide

---

## Task 1: SemVer parser core (parse + compare)

**Files:**
- Create: `cc_extractor/patches/_versions.py`
- Create: `tests/patches/test_versions.py`
- Test: `tests/patches/test_versions.py`

- [ ] **Step 1: Create test file with parser failing tests**

```python
# tests/patches/test_versions.py
import pytest

from cc_extractor.patches._versions import (
    SemverRangeError,
    parse_version,
    version_in_range,
)


def test_parse_version_three_components():
    assert parse_version("2.1.123") == (2, 1, 123)


def test_parse_version_rejects_two_components():
    with pytest.raises(SemverRangeError):
        parse_version("2.1")


def test_parse_version_rejects_non_numeric():
    with pytest.raises(SemverRangeError):
        parse_version("2.0.x")


def test_version_in_range_simple_ge():
    assert version_in_range("2.0.40", ">=2.0.20") is True


def test_version_in_range_simple_lt():
    assert version_in_range("2.0.40", "<2.1.0") is True
    assert version_in_range("2.1.0", "<2.1.0") is False


def test_version_in_range_eq():
    assert version_in_range("2.0.40", "==2.0.40") is True
    assert version_in_range("2.0.41", "==2.0.40") is False


def test_version_in_range_and_clause():
    assert version_in_range("2.0.40", ">=2.0.20,<2.1") is True
    assert version_in_range("2.1.0", ">=2.0.20,<2.1") is False


def test_version_in_range_or_clause():
    expr = ">=2.0.20,<2.1 || >=2.1.0,<3"
    assert version_in_range("2.0.40", expr) is True
    assert version_in_range("2.1.123", expr) is True
    assert version_in_range("2.0.5", expr) is False
    assert version_in_range("3.0.0", expr) is False


def test_version_in_range_rejects_bad_comparator():
    with pytest.raises(SemverRangeError):
        version_in_range("2.0.40", "~=2.0.20")


def test_version_in_range_rejects_bad_version_in_range():
    with pytest.raises(SemverRangeError):
        version_in_range("2.0.40", ">=foo")
```

- [ ] **Step 2: Run tests to verify they fail (module missing)**

Run: `.venv/bin/python -m pytest tests/patches/test_versions.py -v`
Expected: All FAIL with "ModuleNotFoundError: No module named 'cc_extractor.patches._versions'"

- [ ] **Step 3: Implement parser**

Create `cc_extractor/patches/_versions.py`:

```python
"""SemVer range parser scoped to Claude Code's MAJOR.MINOR.PATCH scheme."""

import re
from typing import Iterable, List, Mapping, Optional, Tuple

Version = Tuple[int, int, int]

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_COMPARATOR_RE = re.compile(r"^(>=|<=|==|>|<)\s*(\d+\.\d+\.\d+)$")


class SemverRangeError(ValueError):
    pass


def parse_version(text: str) -> Version:
    if not isinstance(text, str):
        raise SemverRangeError(f"version must be a string, got {type(text).__name__}")
    match = _VERSION_RE.match(text.strip())
    if match is None:
        raise SemverRangeError(f"invalid version: {text!r} (expected MAJOR.MINOR.PATCH)")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


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
            version = parse_version(match.group(2))
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/patches/test_versions.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add cc_extractor/patches/_versions.py tests/patches/test_versions.py
git commit -m "Add SemVer range parser for patch version metadata"
```

---

## Task 2: Range-to-concrete-version resolver

**Files:**
- Modify: `cc_extractor/patches/_versions.py`
- Modify: `tests/patches/test_versions.py`

- [ ] **Step 1: Add failing resolver tests**

Append to `tests/patches/test_versions.py`:

```python
from cc_extractor.patches._versions import resolve_range_to_version


def test_resolve_picks_highest_in_range():
    index = {"binary": {"versions": [
        {"version": "2.0.40"}, {"version": "2.0.45"}, {"version": "2.1.0"}, {"version": "2.1.123"},
    ]}}
    assert resolve_range_to_version(">=2.0.20,<2.1", index=index) == "2.0.45"


def test_resolve_returns_none_when_nothing_matches():
    index = {"binary": {"versions": [{"version": "1.5.0"}]}}
    assert resolve_range_to_version(">=2.0.20,<3", index=index) is None


def test_resolve_skips_malformed_entries():
    index = {"binary": {"versions": [{"version": "2.0.40"}, {"version": "garbage"}, {}]}}
    assert resolve_range_to_version(">=2.0.20,<3", index=index) == "2.0.40"
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/python -m pytest tests/patches/test_versions.py -v`
Expected: 3 new tests FAIL with `ImportError: cannot import name 'resolve_range_to_version'`.

- [ ] **Step 3: Implement resolver**

Append to `cc_extractor/patches/_versions.py`:

```python
def resolve_range_to_version(expr: str, *, index: Mapping[str, object]) -> Optional[str]:
    """Return the highest concrete version in `index` that satisfies `expr`,
    or None if nothing satisfies. `index` follows the schema in
    cc_extractor/data/download-index.seed.json (top-level "binary.versions"
    list of dicts with "version" keys)."""
    binary = index.get("binary") if isinstance(index, Mapping) else None
    versions_list = binary.get("versions") if isinstance(binary, Mapping) else None
    if not isinstance(versions_list, list):
        return None
    candidates: List[Version] = []
    for entry in versions_list:
        if not isinstance(entry, Mapping):
            continue
        text = entry.get("version")
        if not isinstance(text, str):
            continue
        try:
            parsed = parse_version(text)
        except SemverRangeError:
            continue
        try:
            if version_in_range(text, expr):
                candidates.append(parsed)
        except SemverRangeError:
            return None
    if not candidates:
        return None
    best = max(candidates)
    return f"{best[0]}.{best[1]}.{best[2]}"
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `.venv/bin/python -m pytest tests/patches/test_versions.py -v`
Expected: All PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add cc_extractor/patches/_versions.py tests/patches/test_versions.py
git commit -m "Add SemVer range-to-concrete-version resolver"
```

---

## Task 3: Patch types and exceptions

**Files:**
- Modify: `cc_extractor/patches/__init__.py`
- Create: `tests/patches/__init__.py`
- Create: `tests/patches/test_types.py`

- [ ] **Step 1: Create empty test package and failing tests for the new types**

Create `tests/patches/__init__.py` (empty file).

Create `tests/patches/test_types.py`:

```python
from cc_extractor.patches import (
    AggregateResult,
    Patch,
    PatchAnchorMissError,
    PatchBlacklistedError,
    PatchContext,
    PatchOutcome,
    PatchUnsupportedVersionError,
)


def test_patch_is_frozen_dataclass():
    patch = Patch(
        id="x",
        name="X",
        group="ui",
        versions_supported=">=2.0.0,<3",
        versions_tested=(">=2.0.0,<3",),
        apply=lambda js, ctx: PatchOutcome(js=js, status="skipped"),
    )
    assert patch.id == "x"


def test_patch_context_defaults():
    ctx = PatchContext(claude_version=None)
    assert ctx.provider_label == "cc-extractor"
    assert ctx.config == {}
    assert ctx.overlays == {}
    assert ctx.force is False


def test_patch_outcome_default_notes():
    outcome = PatchOutcome(js="x", status="applied")
    assert outcome.notes == ()


def test_aggregate_result_fields():
    result = AggregateResult(
        js="x", applied=("a",), skipped=("b",), missed=("c",), notes=("note",),
    )
    assert result.applied == ("a",)


def test_exceptions_are_value_errors():
    assert issubclass(PatchAnchorMissError, ValueError)
    assert issubclass(PatchBlacklistedError, ValueError)
    assert issubclass(PatchUnsupportedVersionError, ValueError)
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/python -m pytest tests/patches/test_types.py -v`
Expected: FAIL with `ImportError: cannot import name 'AggregateResult' from 'cc_extractor.patches'`.

- [ ] **Step 3: Read existing `__init__.py`, then add new types alongside**

The existing `cc_extractor/patches/__init__.py` defines `PatchResult`, `compute_md5`, etc. Keep all of that. Add new types at the bottom:

```python
# Append to cc_extractor/patches/__init__.py:

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Tuple


@dataclass(frozen=True)
class PatchContext:
    claude_version: Optional[str] = None
    provider_label: str = "cc-extractor"
    config: Mapping[str, Any] = field(default_factory=dict)
    overlays: Mapping[str, str] = field(default_factory=dict)
    force: bool = False


@dataclass(frozen=True)
class PatchOutcome:
    js: str
    status: str  # "applied" | "skipped" | "missed"
    notes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class AggregateResult:
    js: str
    applied: Tuple[str, ...]
    skipped: Tuple[str, ...]
    missed: Tuple[str, ...]
    notes: Tuple[str, ...]


@dataclass(frozen=True)
class Patch:
    id: str
    name: str
    group: str  # "ui" | "thinking" | "prompts" | "tools" | "system"
    versions_supported: str  # SemVer range
    versions_tested: Tuple[str, ...]  # tuple of SemVer ranges, one per matrix bucket
    apply: Callable[[str, "PatchContext"], "PatchOutcome"] = field(repr=False)
    versions_blacklisted: Tuple[str, ...] = ()
    on_miss: str = "fatal"  # "fatal" | "skip" | "warn"


class PatchAnchorMissError(ValueError):
    def __init__(self, patch_id: str, detail: str = ""):
        self.patch_id = patch_id
        self.detail = detail
        super().__init__(f"{patch_id}: anchor not found{(': ' + detail) if detail else ''}")


class PatchUnsupportedVersionError(ValueError):
    def __init__(self, patch_id: str, version: str, supported: str):
        self.patch_id = patch_id
        self.version = version
        self.supported = supported
        super().__init__(f"{patch_id}: version {version} not in supported range {supported!r}")


class PatchBlacklistedError(ValueError):
    def __init__(self, patch_id: str, version: str):
        self.patch_id = patch_id
        self.version = version
        super().__init__(f"{patch_id}: version {version} is blacklisted")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/patches/test_types.py -v`
Expected: All 5 tests PASS.

Also run the full existing suite to confirm no regressions:

Run: `.venv/bin/python -m pytest -q`
Expected: All existing tests PASS (no symbols removed from `cc_extractor.patches`).

- [ ] **Step 5: Commit**

```bash
git add cc_extractor/patches/__init__.py tests/patches/__init__.py tests/patches/test_types.py
git commit -m "Add Patch dataclasses and exceptions"
```

---

## Task 4: Empty registry + apply_patches function

**Files:**
- Create: `cc_extractor/patches/_registry.py`
- Modify: `cc_extractor/patches/__init__.py`
- Create: `tests/patches/test_apply.py`

- [ ] **Step 1: Create failing apply_patches tests**

Create `tests/patches/test_apply.py`:

```python
import warnings
import pytest

from cc_extractor.patches import (
    AggregateResult,
    Patch,
    PatchAnchorMissError,
    PatchBlacklistedError,
    PatchContext,
    PatchOutcome,
    PatchUnsupportedVersionError,
    apply_patches,
)


def _make_patch(id_, *, status="applied", on_miss="fatal", supported=">=0.0.0,<99",
                tested=(">=0.0.0,<99",), blacklisted=()):
    def _apply(js, ctx):
        return PatchOutcome(js=js + f":{id_}" if status == "applied" else js, status=status)
    return Patch(
        id=id_, name=id_, group="ui",
        versions_supported=supported,
        versions_tested=tested,
        versions_blacklisted=blacklisted,
        on_miss=on_miss,
        apply=_apply,
    )


def test_apply_patches_runs_in_registry_order():
    registry = {"a": _make_patch("a"), "b": _make_patch("b")}
    ctx = PatchContext(claude_version=None)
    result = apply_patches("js", ["a", "b"], ctx, registry=registry)
    assert result.js == "js:a:b"
    assert result.applied == ("a", "b")


def test_apply_patches_skips_when_outcome_is_skipped():
    registry = {"a": _make_patch("a", status="skipped")}
    ctx = PatchContext(claude_version=None)
    result = apply_patches("js", ["a"], ctx, registry=registry)
    assert result.js == "js"
    assert result.applied == ()
    assert result.skipped == ("a",)


def test_apply_patches_fatal_miss_raises():
    registry = {"a": _make_patch("a", status="missed", on_miss="fatal")}
    ctx = PatchContext(claude_version=None)
    with pytest.raises(PatchAnchorMissError):
        apply_patches("js", ["a"], ctx, registry=registry)


def test_apply_patches_warn_miss_warns_and_continues():
    registry = {"a": _make_patch("a", status="missed", on_miss="warn"),
                "b": _make_patch("b")}
    ctx = PatchContext(claude_version=None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = apply_patches("js", ["a", "b"], ctx, registry=registry)
    assert result.applied == ("b",)
    assert result.missed == ("a",)
    assert any("a" in str(w.message) for w in caught)


def test_apply_patches_skip_miss_silent():
    registry = {"a": _make_patch("a", status="missed", on_miss="skip")}
    ctx = PatchContext(claude_version=None)
    result = apply_patches("js", ["a"], ctx, registry=registry)
    assert result.missed == ("a",)
    assert result.applied == ()
    assert result.skipped == ()


def test_apply_patches_blacklist_blocks():
    registry = {"a": _make_patch("a", blacklisted=("2.0.40",))}
    ctx = PatchContext(claude_version="2.0.40")
    with pytest.raises(PatchBlacklistedError):
        apply_patches("js", ["a"], ctx, registry=registry)


def test_apply_patches_unsupported_version_blocks():
    registry = {"a": _make_patch("a", supported=">=3.0.0,<4")}
    ctx = PatchContext(claude_version="2.0.40")
    with pytest.raises(PatchUnsupportedVersionError):
        apply_patches("js", ["a"], ctx, registry=registry)


def test_apply_patches_force_bypasses_blacklist():
    registry = {"a": _make_patch("a", blacklisted=("2.0.40",))}
    ctx = PatchContext(claude_version="2.0.40", force=True)
    result = apply_patches("js", ["a"], ctx, registry=registry)
    assert result.applied == ("a",)


def test_apply_patches_warns_when_version_supported_but_not_tested():
    registry = {"a": _make_patch("a", supported=">=2.0.0,<3", tested=(">=2.0.0,<2.1",))}
    ctx = PatchContext(claude_version="2.5.0")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = apply_patches("js", ["a"], ctx, registry=registry)
    assert result.applied == ("a",)
    assert any("2.5.0" in str(w.message) for w in caught)


def test_apply_patches_unknown_id_raises():
    with pytest.raises(KeyError):
        apply_patches("js", ["nope"], PatchContext(claude_version=None), registry={})
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/python -m pytest tests/patches/test_apply.py -v`
Expected: FAIL with `ImportError: cannot import name 'apply_patches'`.

- [ ] **Step 3: Create empty registry**

Create `cc_extractor/patches/_registry.py`:

```python
"""Explicit registry of `cc_extractor.patches` Patch objects.

Each migrated patch module exposes a `PATCH` constant. This file imports
them and assembles the `REGISTRY` dict keyed by patch id. Order matters:
`apply_patches` runs requested ids in the order they appear in REGISTRY
when the caller does not specify an order.
"""

from typing import Dict

from . import Patch  # type: ignore[attr-defined]

REGISTRY: Dict[str, "Patch"] = {}


def get_patch(patch_id: str) -> "Patch":
    if patch_id not in REGISTRY:
        raise KeyError(f"unknown patch: {patch_id!r}")
    return REGISTRY[patch_id]


def registered_ids() -> tuple:
    return tuple(REGISTRY.keys())
```

- [ ] **Step 4: Implement `apply_patches`**

Append to `cc_extractor/patches/__init__.py`:

```python
import logging
import warnings
from typing import List, Mapping as _Mapping, Optional as _Optional, Sequence

from ._versions import SemverRangeError, version_in_range


_log = logging.getLogger(__name__)


def apply_patches(
    js: str,
    ids: Sequence[str],
    ctx: "PatchContext",
    *,
    registry: _Optional[_Mapping[str, "Patch"]] = None,
) -> "AggregateResult":
    if registry is None:
        from ._registry import REGISTRY as _REGISTRY  # late import: avoids cycle
        registry = _REGISTRY

    applied: List[str] = []
    skipped: List[str] = []
    missed: List[str] = []
    notes: List[str] = []

    for patch_id in ids:
        if patch_id not in registry:
            raise KeyError(f"unknown patch: {patch_id!r}")
        patch = registry[patch_id]
        _preflight(patch, ctx)
        outcome = patch.apply(js, ctx)
        if outcome.status == "applied":
            applied.append(patch_id)
            js = outcome.js
        elif outcome.status == "skipped":
            skipped.append(patch_id)
        elif outcome.status == "missed":
            if patch.on_miss == "fatal":
                raise PatchAnchorMissError(patch_id)
            if patch.on_miss == "warn":
                warnings.warn(
                    f"patch {patch_id!r}: anchor not found",
                    UserWarning,
                    stacklevel=2,
                )
            missed.append(patch_id)
        else:
            raise ValueError(f"patch {patch_id!r} returned unknown status {outcome.status!r}")
        notes.extend(outcome.notes)

    return AggregateResult(
        js=js,
        applied=tuple(applied),
        skipped=tuple(skipped),
        missed=tuple(missed),
        notes=tuple(notes),
    )


def _preflight(patch: "Patch", ctx: "PatchContext") -> None:
    version = ctx.claude_version
    if version is None:
        _log.debug("apply_patches: no claude_version provided, skipping pre-flight for %s", patch.id)
        return

    if version in patch.versions_blacklisted and not ctx.force:
        raise PatchBlacklistedError(patch.id, version)

    try:
        in_supported = version_in_range(version, patch.versions_supported)
    except SemverRangeError as exc:
        raise PatchUnsupportedVersionError(patch.id, version, patch.versions_supported) from exc

    if not in_supported and not ctx.force:
        raise PatchUnsupportedVersionError(patch.id, version, patch.versions_supported)

    in_tested = False
    for tested_range in patch.versions_tested:
        try:
            if version_in_range(version, tested_range):
                in_tested = True
                break
        except SemverRangeError:
            continue
    if not in_tested:
        warnings.warn(
            f"patch {patch.id!r} not tested against version {version}; "
            f"tested ranges: {list(patch.versions_tested)}",
            UserWarning,
            stacklevel=2,
        )
```

- [ ] **Step 5: Run tests to verify all pass**

Run: `.venv/bin/python -m pytest tests/patches/ -v`
Expected: All PASS (versions + types + apply).

Run: `.venv/bin/python -m pytest -q`
Expected: All existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add cc_extractor/patches/_registry.py cc_extractor/patches/__init__.py tests/patches/test_apply.py
git commit -m "Add apply_patches with version pre-flight and miss handling"
```

---

## Task 5: Pinned ranges + range resolver pytest helper

**Files:**
- Create: `tests/patches/_pinned.py`
- Create: `tests/patches/conftest.py`

- [ ] **Step 1: Create the pinned ranges module**

Create `tests/patches/_pinned.py`:

```python
"""Default test-matrix version ranges, resolved at test collection time."""

DEFAULT_VERSION_RANGES = (">=2.0.20,<2.1", ">=2.1.0,<3")
```

- [ ] **Step 2: Create the conftest with helpers (no fixtures yet, those come in Task 6)**

Create `tests/patches/conftest.py`:

```python
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
```

- [ ] **Step 3: Smoke-test the helper from a Python REPL or quick test**

Run: `.venv/bin/python -c "from tests.patches.conftest import resolve_tested_versions; print('ok')"`
Expected: prints `ok` (import succeeds).

- [ ] **Step 4: Commit**

```bash
git add tests/patches/_pinned.py tests/patches/conftest.py
git commit -m "Add default version ranges and tested-version resolver helper"
```

---

## Task 6: cli_js_real and parse_js fixtures

**Files:**
- Modify: `tests/patches/conftest.py`
- Create: `tests/patches/test_fixtures.py`

- [ ] **Step 1: Add failing test for cli_js_real**

Create `tests/patches/test_fixtures.py`:

```python
import pytest

from cc_extractor.download_index import load_download_index
from cc_extractor.patches._versions import resolve_range_to_version


pytestmark = pytest.mark.skipif(
    resolve_range_to_version(">=2.0.0,<3", index=load_download_index()) is None,
    reason="no Claude Code binary version available in download index",
)


def test_cli_js_real_returns_string(cli_js_real):
    version = resolve_range_to_version(">=2.0.0,<3", index=load_download_index())
    js = cli_js_real(version)
    assert isinstance(js, str)
    assert len(js) > 1000


def test_parse_js_accepts_valid(parse_js):
    parse_js("function x(){return 1;}")


def test_parse_js_rejects_invalid(parse_js):
    with pytest.raises(Exception):
        parse_js("function x(){return")
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/python -m pytest tests/patches/test_fixtures.py -v`
Expected: FAIL with `fixture 'cli_js_real' not found`.

- [ ] **Step 3: Implement fixtures in conftest**

Append to `tests/patches/conftest.py`:

```python
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

import pytest

from cc_extractor.bun_extract import parse_bun_binary
from cc_extractor.download_index import download_version_entry, load_download_index
from cc_extractor.downloader import download_native_binary, get_platform_key
from cc_extractor.workspace import workspace_root


_CLI_JS_CACHE = {}


def _extract_cli_js(binary_path: Path) -> str:
    data = binary_path.read_bytes()
    info = parse_bun_binary(data)
    for module in info.modules:
        if module.name and module.name.endswith("cli.js"):
            return data[module.data_offset : module.data_offset + module.data_size].decode(
                "utf-8", errors="replace"
            )
    raise RuntimeError(f"cli.js not found inside {binary_path}")


@pytest.fixture(scope="session")
def cli_js_real() -> Callable[[str], str]:
    def loader(version: str) -> str:
        if version in _CLI_JS_CACHE:
            return _CLI_JS_CACHE[version]
        index = load_download_index()
        entry = download_version_entry(index, version, kind="binary")
        if entry is None:
            pytest.skip(f"version {version} not present in download index")
        platform_key = get_platform_key()
        binary_path = download_native_binary(version=version, platform_key=platform_key)
        js = _extract_cli_js(Path(binary_path))
        _CLI_JS_CACHE[version] = js
        return js
    return loader


@pytest.fixture(scope="session")
def parse_js() -> Callable[[str], None]:
    node = shutil.which("node")
    if node is None:
        def _skip(_js: str) -> None:
            pytest.skip("node not on PATH; skipping L2 parse check")
        return _skip

    def runner(js: str) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fp:
            fp.write(js)
            tmp_path = fp.name
        try:
            result = subprocess.run(
                [node, "--check", tmp_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise AssertionError(
                    f"node --check failed: {result.stderr.strip() or result.stdout.strip()}"
                )
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    return runner
```

Verify the `download_native_binary` import name and signature against the actual `cc_extractor/downloader.py`. If the function has a different name (e.g., `download_binary` or `fetch_binary`), update the import + call accordingly.

- [ ] **Step 4: Verify downloader signature**

Run: `.venv/bin/python -c "from cc_extractor.downloader import download_native_binary; help(download_native_binary)"`
Expected: prints the function signature. If `ImportError`, run `grep -n '^def ' cc_extractor/downloader.py` and pick the function whose name and docstring describe "download a Claude Code binary by version, return the local path." Update conftest accordingly.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/patches/test_fixtures.py -v`
Expected: tests PASS, or are SKIPPED with a clear message if the download index is empty / Node is missing.

- [ ] **Step 6: Commit**

```bash
git add tests/patches/conftest.py tests/patches/test_fixtures.py
git commit -m "Add cli_js_real and parse_js fixtures for L1+L2 patch tests"
```

---

## Task 7: cli_js_synthetic fixture and synthetic snippets

**Files:**
- Create: `tests/patches/fixtures/__init__.py`
- Create: `tests/patches/fixtures/synthetic.py`
- Modify: `tests/patches/conftest.py`

- [ ] **Step 1: Create the synthetic snippets module**

Create `tests/patches/fixtures/__init__.py` (empty).

Create `tests/patches/fixtures/synthetic.py`:

```python
"""Hand-crafted JS snippets per patch.

Each snippet is the smallest possible chunk that exercises the patch's
anchor regex. They are NOT minified Claude Code; they exist for fast
iteration during a port and for catching obvious anchor breakages
without downloading a real binary."""

SYNTHETIC = {
    "hide-startup-banner": (
        ',R.createElement(B,{isBeforeFirstMessage:!1}),'
        'function banner(){if(x)return"Apple_Terminal";return"Welcome to Claude Code"}'
    ),
    "hide-startup-clawd": (
        'function inner(){return"\\u259B\\u2588\\u2588\\u2588\\u259C"}'
        'function wrapper(){return R.createElement(inner,{})}'
    ),
    "hide-ctrl-g-to-edit": 'if(v&&P)p("tengu_external_editor_hint_shown",{})',
    "show-more-items-in-select-menus": 'function menu({visibleOptionCount:A=5}){return A}',
    "model-customizations": (
        'function models(){let L=[]; '
        'L.push({value:M,label:N,description:"Custom model"});return L}'
    ),
    "suppress-line-numbers": (
        'function fmt({content:C,startLine:S}){if(!C)return"";'
        'let L=C.split(/\\r?\\n/);return L.map(x=>x).join("\\n")}function next(){}'
    ),
    "auto-accept-plan-mode": (
        'function plan(){return R.createElement(Box,'
        '{title:"Ready to code?",onChange:onPick,onCancel:onCancel})}'
    ),
    "allow-custom-agent-models": (
        ',model:z.enum(MODELS).optional();'
        'let ok=K&&typeof K==="string"&&MODELS.includes(K)'
    ),
    "patches-applied-indication": 'const version=`${pkg.VERSION} (Claude Code)`;',
    "themes": "\n".join([
        'function getNames(){return{"dark":"Dark mode","light":"Light mode"}}',
        'const themeOptions=[{label:"Dark mode",value:"dark"},'
        '{label:"Light mode",value:"light"}];',
        'function pickTheme(A){switch(A){case"light":return LX9;'
        'case"dark":return CX9;default:return CX9}}',
    ]),
    "prompt-overlays": (
        'let WEBFETCH=`Fetches URLs.\\n'
        '- For GitHub URLs, prefer using the gh CLI via Bash instead '
        '(e.g., gh pr view, gh issue view, gh api).`;'
    ),
}
```

- [ ] **Step 2: Add the fixture**

Append to `tests/patches/conftest.py`:

```python
@pytest.fixture
def cli_js_synthetic():
    from tests.patches.fixtures.synthetic import SYNTHETIC

    def loader(patch_id: str) -> str:
        if patch_id not in SYNTHETIC:
            raise KeyError(f"no synthetic snippet for patch {patch_id!r}")
        return SYNTHETIC[patch_id]
    return loader
```

- [ ] **Step 3: Verify the fixture loads**

Run: `.venv/bin/python -c "from tests.patches.fixtures.synthetic import SYNTHETIC; print(len(SYNTHETIC), 'snippets')"`
Expected: prints `11 snippets`.

- [ ] **Step 4: Commit**

```bash
git add tests/patches/fixtures/__init__.py tests/patches/fixtures/synthetic.py tests/patches/conftest.py
git commit -m "Add synthetic JS snippets fixture for fast patch tests"
```

---

## Task 8: Registry-level invariants test

**Files:**
- Create: `tests/patches/test_registry.py`

- [ ] **Step 1: Write the test file**

Create `tests/patches/test_registry.py`:

```python
"""Cross-patch invariants. Runs against the live registry; passes against
an empty registry too."""

from cc_extractor.patches._registry import REGISTRY
from cc_extractor.patches._versions import (
    SemverRangeError,
    parse_range,
    range_contains_range,
    resolve_range_to_version,
)


def test_no_duplicate_ids():
    assert len(REGISTRY) == len(set(REGISTRY.keys()))


def test_each_versions_supported_parses():
    for patch in REGISTRY.values():
        parse_range(patch.versions_supported)  # raises on invalid


def test_each_versions_tested_entry_parses():
    for patch in REGISTRY.values():
        for tested in patch.versions_tested:
            parse_range(tested)


def test_versions_tested_is_non_empty():
    for patch in REGISTRY.values():
        assert patch.versions_tested, f"{patch.id} has empty versions_tested"


def test_versions_tested_subset_of_versions_supported():
    for patch in REGISTRY.values():
        for tested in patch.versions_tested:
            assert range_contains_range(patch.versions_supported, tested), (
                f"{patch.id}: tested range {tested!r} not contained in "
                f"supported range {patch.versions_supported!r}"
            )


def test_blacklisted_versions_do_not_satisfy_tested():
    from cc_extractor.patches._versions import version_in_range
    for patch in REGISTRY.values():
        for blacklisted in patch.versions_blacklisted:
            for tested in patch.versions_tested:
                try:
                    in_range = version_in_range(blacklisted, tested)
                except SemverRangeError:
                    continue
                assert not in_range, (
                    f"{patch.id}: blacklisted version {blacklisted} satisfies "
                    f"tested range {tested!r}"
                )


def test_each_versions_tested_resolves_to_concrete_version():
    from cc_extractor.download_index import load_download_index
    index = load_download_index()
    if not index.get("binary", {}).get("versions"):
        return  # empty index: pre-flight succeeded; nothing else to assert
    for patch in REGISTRY.values():
        any_resolved = any(
            resolve_range_to_version(tested, index=index) is not None
            for tested in patch.versions_tested
        )
        assert any_resolved, (
            f"{patch.id}: no entry in versions_tested resolves to a concrete "
            f"version in the current download index"
        )
```

- [ ] **Step 2: Run tests (registry empty so all pass trivially)**

Run: `.venv/bin/python -m pytest tests/patches/test_registry.py -v`
Expected: All PASS (registry is empty; loops don't execute).

- [ ] **Step 3: Commit**

```bash
git add tests/patches/test_registry.py
git commit -m "Add registry-level patch invariant tests"
```

---

## Task 9: Migrate hide-startup-banner (worked example)

**Files:**
- Create: `cc_extractor/patches/hide_startup_banner.py`
- Modify: `cc_extractor/patches/_registry.py`
- Modify: `cc_extractor/variants/tweaks.py`
- Create: `tests/patches/test_hide_startup_banner.py`

- [ ] **Step 1: Write the failing patch test**

Create `tests/patches/test_hide_startup_banner.py`:

```python
import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.hide_startup_banner import PATCH


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("hide-startup-banner")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert "isBeforeFirstMessage" not in outcome.js or "return null;" in outcome.js


def test_metadata():
    assert PATCH.id == "hide-startup-banner"
    assert PATCH.group == "ui"
    assert PATCH.versions_tested  # non-empty


@pytest.fixture
def real_js_versions():
    from tests.patches.conftest import resolve_tested_versions
    return resolve_tested_versions(PATCH)


def test_real_l1_anchor_matches(cli_js_real, real_js_versions):
    if not real_js_versions:
        pytest.skip("no resolved versions")
    for version in real_js_versions:
        js = cli_js_real(version)
        outcome = PATCH.apply(js, PatchContext(claude_version=version))
        assert outcome.status == "applied", (
            f"hide-startup-banner did not apply against {version}"
        )


def test_real_l2_patched_js_parses(cli_js_real, real_js_versions, parse_js):
    if not real_js_versions:
        pytest.skip("no resolved versions")
    for version in real_js_versions:
        js = cli_js_real(version)
        outcome = PATCH.apply(js, PatchContext(claude_version=version))
        parse_js(outcome.js)
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/python -m pytest tests/patches/test_hide_startup_banner.py -v`
Expected: FAIL with `ModuleNotFoundError: cc_extractor.patches.hide_startup_banner`.

- [ ] **Step 3: Create the patch module**

Create `cc_extractor/patches/hide_startup_banner.py`:

```python
"""Hide the startup banner / welcome screen.

Adapted from cc_extractor/variants/tweaks.py::_hide_startup_banner.
Original tweakcc source: vendor/tweakcc/src/patches/hideStartupBanner.ts.
"""

import re

from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    match = re.search(r",[$\w]+\.createElement\([$\w]+,\{isBeforeFirstMessage:!1\}\),", js)
    if match:
        new_js = js[:match.start()] + "," + js[match.end():]
        return PatchOutcome(js=new_js, status="applied")

    for match in re.finditer(r"(function ([$\w]+)\(\)\{)(?=[^}]{0,500}Apple_Terminal)", js):
        body_start = match.end()
        if "Welcome to Claude Code" in js[body_start:body_start + 5000]:
            new_js = js[:body_start] + "return null;" + js[body_start:]
            return PatchOutcome(js=new_js, status="applied")
    return PatchOutcome(js=js, status="missed")


PATCH = Patch(
    id="hide-startup-banner",
    name="Hide startup banner",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
)
```

- [ ] **Step 4: Add the shared default-ranges module (so each patch can import it)**

Create `cc_extractor/patches/_pinned_default.py`:

```python
"""Default versions_tested ranges shared by most patches."""

DEFAULT_VERSION_RANGES = (">=2.0.20,<2.1", ">=2.1.0,<3")
```

- [ ] **Step 5: Register in `_registry.py`**

Replace `cc_extractor/patches/_registry.py` with:

```python
"""Explicit registry of `cc_extractor.patches` Patch objects."""

from typing import Dict

from . import Patch
from . import hide_startup_banner

REGISTRY: Dict[str, Patch] = {
    hide_startup_banner.PATCH.id: hide_startup_banner.PATCH,
}


def get_patch(patch_id: str) -> Patch:
    if patch_id not in REGISTRY:
        raise KeyError(f"unknown patch: {patch_id!r}")
    return REGISTRY[patch_id]


def registered_ids() -> tuple:
    return tuple(REGISTRY.keys())
```

- [ ] **Step 6: Update the shim in `variants/tweaks.py` to delegate this id to the registry**

Open `cc_extractor/variants/tweaks.py`. Find the `_PATCHERS` dict and the `apply_variant_tweaks` function. Modify the loop in `apply_variant_tweaks` so that when a `tweak_id` is `"hide-startup-banner"`, it routes to the new registry instead of `_PATCHERS`. Patch must still pass through `applied`/`skipped` lists.

Insert near the top of `apply_variant_tweaks`, after `missing: List[str] = []`:

```python
    from ..patches import PatchContext as _PatchCtx, apply_patches as _apply_patches
    from ..patches._registry import REGISTRY as _PATCH_REGISTRY
```

Replace the tail of the loop body in `apply_variant_tweaks` (the `else: patcher = _PATCHERS[tweak_id]; ...` branch) with:

```python
        elif tweak_id in _PATCH_REGISTRY:
            sub = _apply_patches(
                js,
                [tweak_id],
                _PatchCtx(
                    claude_version=None,
                    provider_label=provider_label,
                    config=config,
                    overlays=overlays,
                ),
                registry=_PATCH_REGISTRY,
            )
            js = sub.js
            if sub.applied:
                applied.append(tweak_id)
            else:
                skipped.append(tweak_id)
        else:
            patcher = _PATCHERS[tweak_id]
            patched = patcher(js, provider_label=provider_label)
            if patched is None:
                raise TweakPatchError(tweak_id, "failed to find anchor")
            js = patched
            if js != old_js:
                applied.append(tweak_id)
            else:
                skipped.append(tweak_id)
```

Remove the entry for `"hide-startup-banner"` from the `_PATCHERS` dict at the bottom of the file. Leave `_hide_startup_banner` defined for now (unused; later cleanup).

- [ ] **Step 7: Run the new test + the existing variant_tweaks suite to confirm no regression**

Run: `.venv/bin/python -m pytest tests/patches/test_hide_startup_banner.py tests/test_variant_tweaks.py -v`
Expected: All PASS. The existing `test_curated_tweak_ports_patch_fixture_patterns` test (which exercises `hide-startup-banner` among others) still passes.

- [ ] **Step 8: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: All PASS.

- [ ] **Step 9: Commit**

```bash
git add cc_extractor/patches/hide_startup_banner.py cc_extractor/patches/_pinned_default.py cc_extractor/patches/_registry.py cc_extractor/variants/tweaks.py tests/patches/test_hide_startup_banner.py
git commit -m "Migrate hide-startup-banner to per-file patch module"
```

---

## Task 10: Migrate show-more-items

**Files:**
- Create: `cc_extractor/patches/show_more_items.py`
- Modify: `cc_extractor/patches/_registry.py`
- Modify: `cc_extractor/variants/tweaks.py`
- Create: `tests/patches/test_show_more_items.py`

- [ ] **Step 1: Write the test**

Create `tests/patches/test_show_more_items.py`:

```python
import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.show_more_items import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("show-more-items-in-select-menus")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert "visibleOptionCount:A=25" in outcome.js


def test_metadata():
    assert PATCH.id == "show-more-items-in-select-menus"
    assert PATCH.group == "ui"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l1(cli_js_real, version):
    js = cli_js_real(version)
    outcome = PATCH.apply(js, PatchContext(claude_version=version))
    assert outcome.status == "applied"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l2(cli_js_real, version, parse_js):
    js = cli_js_real(version)
    outcome = PATCH.apply(js, PatchContext(claude_version=version))
    parse_js(outcome.js)
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/python -m pytest tests/patches/test_show_more_items.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create the patch module**

Create `cc_extractor/patches/show_more_items.py`:

```python
"""Increase visibleOptionCount in select menus.

Adapted from cc_extractor/variants/tweaks.py::_show_more_items.
"""

import re

from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    matches = list(re.finditer(r"visibleOptionCount:[$\w]+=(\d+)", js))
    if not matches:
        return PatchOutcome(js=js, status="missed")
    new_js = js
    for match in reversed(matches):
        start = match.start(1)
        new_js = new_js[:start] + "25" + new_js[match.end(1):]
    height = re.search(
        r"(\{rows:([$\w]+),columns:[$\w]+\}=[$\w]+\(\),)([$\w]+)=Math\.floor\(\2/2\)",
        new_js,
    )
    if height:
        new_js = (
            new_js[:height.start()]
            + f"{height.group(1)}{height.group(3)}={height.group(2)}"
            + new_js[height.end():]
        )
    replacements = [
        (r"Math\.max\(1,Math\.floor\(\(([$\w]+)-10\)/2\)\)", r"Math.max(1,\1-3)"),
        (r"Math\.min\(6,Math\.max\(1,([$\w]+)-3\)\)", r"Math.max(1,\1-3)"),
    ]
    for pattern, repl in replacements:
        new_js = re.sub(pattern, repl, new_js, count=1)
    return PatchOutcome(js=new_js, status="applied")


PATCH = Patch(
    id="show-more-items-in-select-menus",
    name="Show more items in select menus",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
)
```

- [ ] **Step 4: Register**

Modify `cc_extractor/patches/_registry.py`. Add import and entry:

```python
from . import hide_startup_banner, show_more_items

REGISTRY: Dict[str, Patch] = {
    hide_startup_banner.PATCH.id: hide_startup_banner.PATCH,
    show_more_items.PATCH.id: show_more_items.PATCH,
}
```

- [ ] **Step 5: Update shim**

In `cc_extractor/variants/tweaks.py`, remove `"show-more-items-in-select-menus"` from `_PATCHERS` dict.

- [ ] **Step 6: Run tests**

Run: `.venv/bin/python -m pytest tests/patches/test_show_more_items.py tests/test_variant_tweaks.py -v`
Expected: All PASS.

Run: `.venv/bin/python -m pytest -q`
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add cc_extractor/patches/show_more_items.py cc_extractor/patches/_registry.py cc_extractor/variants/tweaks.py tests/patches/test_show_more_items.py
git commit -m "Migrate show-more-items-in-select-menus to per-file module"
```

---

## Task 11: Migrate model-customizations

**Files:**
- Create: `cc_extractor/patches/model_customizations.py`
- Modify: `cc_extractor/patches/_registry.py`
- Modify: `cc_extractor/variants/tweaks.py`
- Create: `tests/patches/test_model_customizations.py`

- [ ] **Step 1: Write the test**

Create `tests/patches/test_model_customizations.py`:

```python
import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.model_customizations import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("model-customizations")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert "claude-sonnet-4-6" in outcome.js


def test_metadata():
    assert PATCH.id == "model-customizations"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l1(cli_js_real, version):
    js = cli_js_real(version)
    outcome = PATCH.apply(js, PatchContext(claude_version=version))
    assert outcome.status == "applied"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l2(cli_js_real, version, parse_js):
    js = cli_js_real(version)
    outcome = PATCH.apply(js, PatchContext(claude_version=version))
    parse_js(outcome.js)
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/python -m pytest tests/patches/test_model_customizations.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create the module**

Create `cc_extractor/patches/model_customizations.py`:

```python
"""Add custom Claude model entries to the model picker.

Adapted from cc_extractor/variants/tweaks.py::_model_customizations.
"""

import json
import re

from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


CUSTOM_MODELS = [
    {"value": "claude-opus-4-6", "label": "Opus 4.6", "description": "Claude Opus 4.6"},
    {"value": "claude-sonnet-4-6", "label": "Sonnet 4.6", "description": "Claude Sonnet 4.6"},
    {"value": "claude-haiku-4-5-20251001", "label": "Haiku 4.5", "description": "Claude Haiku 4.5"},
    {"value": "claude-opus-4-5-20251101", "label": "Opus 4.5", "description": "Claude Opus 4.5"},
    {"value": "claude-sonnet-4-5-20250929", "label": "Sonnet 4.5", "description": "Claude Sonnet 4.5"},
    {"value": "claude-opus-4-20250514", "label": "Opus 4", "description": "Claude Opus 4"},
    {"value": "claude-sonnet-4-20250514", "label": "Sonnet 4", "description": "Claude Sonnet 4"},
    {"value": "claude-3-7-sonnet-20250219", "label": "Sonnet 3.7", "description": "Claude 3.7 Sonnet"},
    {"value": "claude-3-5-haiku-20241022", "label": "Haiku 3.5", "description": "Claude 3.5 Haiku"},
]


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    match = re.search(
        r" ([$\w]+)\.push\(\{value:[$\w]+,label:[$\w]+,description:\"Custom model\"\}\)", js
    )
    if not match:
        return PatchOutcome(js=js, status="missed")
    model_var = match.group(1)
    search_start = max(0, match.start() - 1500)
    chunk = js[search_start:match.start()]
    func_pattern = re.compile(
        rf"function [$\w]+\([^)]*\)\{{(?:let|var|const) {re.escape(model_var)}=.+?;"
    )
    last = None
    for found in func_pattern.finditer(chunk):
        last = found
    if last is None:
        return PatchOutcome(js=js, status="missed")
    insertion_index = search_start + last.end()
    inject = "".join(
        f"{model_var}.push({json.dumps(model, separators=(',', ':'))});"
        for model in CUSTOM_MODELS
    )
    new_js = js[:insertion_index] + inject + js[insertion_index:]
    return PatchOutcome(js=new_js, status="applied")


PATCH = Patch(
    id="model-customizations",
    name="Custom Claude models in picker",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
)
```

- [ ] **Step 4: Register and update shim**

In `_registry.py`, add `model_customizations` import and entry. In `variants/tweaks.py`, remove `"model-customizations"` from `_PATCHERS`.

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/patches/test_model_customizations.py tests/test_variant_tweaks.py -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add cc_extractor/patches/model_customizations.py cc_extractor/patches/_registry.py cc_extractor/variants/tweaks.py tests/patches/test_model_customizations.py
git commit -m "Migrate model-customizations to per-file module"
```

---

## Task 12: Migrate hide-startup-clawd

**Files:**
- Create: `cc_extractor/patches/hide_startup_clawd.py`
- Modify: `cc_extractor/patches/_registry.py`
- Modify: `cc_extractor/variants/tweaks.py`
- Create: `tests/patches/test_hide_startup_clawd.py`

- [ ] **Step 1: Test**

Create `tests/patches/test_hide_startup_clawd.py`:

```python
import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.hide_startup_clawd import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("hide-startup-clawd")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert "return null;" in outcome.js


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l1(cli_js_real, version):
    js = cli_js_real(version)
    outcome = PATCH.apply(js, PatchContext(claude_version=version))
    assert outcome.status == "applied"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l2(cli_js_real, version, parse_js):
    js = cli_js_real(version)
    outcome = PATCH.apply(js, PatchContext(claude_version=version))
    parse_js(outcome.js)
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/python -m pytest tests/patches/test_hide_startup_clawd.py -v`
Expected: FAIL.

- [ ] **Step 3: Create module**

Create `cc_extractor/patches/hide_startup_clawd.py`:

```python
"""Hide the ASCII clawed-claw startup banner.

Adapted from cc_extractor/variants/tweaks.py::_hide_startup_clawd.
"""

import re

from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    match = re.search(r"▛███▜|\\u259B\\u2588\\u2588\\u2588\\u259C", js, re.IGNORECASE)
    if not match:
        return PatchOutcome(js=js, status="missed")
    lookback_start = max(0, match.start() - 2000)
    before = js[lookback_start:match.start()]
    funcs = list(re.finditer(r"function ([$\w]+)\([^)]*\)\{", before))
    if not funcs:
        return PatchOutcome(js=js, status="missed")
    inner_name = funcs[-1].group(1)
    for wrapper in re.finditer(r"function ([$\w]+)\([^)]*\)\{", js):
        body_start = wrapper.end()
        body = js[body_start:body_start + 500]
        elem_idx = body.find(f"createElement({inner_name},")
        if elem_idx == -1:
            continue
        next_func_idx = body.find("function ")
        if next_func_idx != -1 and next_func_idx < elem_idx:
            continue
        new_js = js[:body_start] + "return null;" + js[body_start:]
        return PatchOutcome(js=new_js, status="applied")
    inner_start = lookback_start + funcs[-1].end()
    new_js = js[:inner_start] + "return null;" + js[inner_start:]
    return PatchOutcome(js=new_js, status="applied")


PATCH = Patch(
    id="hide-startup-clawd",
    name="Hide ASCII startup banner",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
)
```

- [ ] **Step 4: Register and update shim** (same pattern as Task 10/11)

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add cc_extractor/patches/hide_startup_clawd.py cc_extractor/patches/_registry.py cc_extractor/variants/tweaks.py tests/patches/test_hide_startup_clawd.py
git commit -m "Migrate hide-startup-clawd to per-file module"
```

---

## Task 13: Migrate hide-ctrl-g-to-edit

**Files:**
- Create: `cc_extractor/patches/hide_ctrl_g.py`
- Modify: `cc_extractor/patches/_registry.py`
- Modify: `cc_extractor/variants/tweaks.py`
- Create: `tests/patches/test_hide_ctrl_g.py`

- [ ] **Step 1: Test**

Create `tests/patches/test_hide_ctrl_g.py`:

```python
import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.hide_ctrl_g import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("hide-ctrl-g-to-edit")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert 'if(false)p("tengu_external_editor_hint_shown"' in outcome.js


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l1(cli_js_real, version):
    outcome = PATCH.apply(cli_js_real(version), PatchContext(claude_version=version))
    assert outcome.status == "applied"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l2(cli_js_real, version, parse_js):
    outcome = PATCH.apply(cli_js_real(version), PatchContext(claude_version=version))
    parse_js(outcome.js)
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/python -m pytest tests/patches/test_hide_ctrl_g.py -v`
Expected: FAIL.

- [ ] **Step 3: Create module**

Create `cc_extractor/patches/hide_ctrl_g.py`:

```python
"""Hide the 'press Ctrl+G to edit' hint."""

import re

from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    match = re.search(
        r"if\(([$\w]+&&[$\w]+)\)[$\w]+\(\"tengu_external_editor_hint_shown\",",
        js,
    )
    if not match:
        return PatchOutcome(js=js, status="missed")
    new_js = js[:match.start(1)] + "false" + js[match.end(1):]
    return PatchOutcome(js=new_js, status="applied")


PATCH = Patch(
    id="hide-ctrl-g-to-edit",
    name="Hide Ctrl+G edit hint",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
)
```

- [ ] **Step 4: Register, update shim, run tests, commit** (same pattern)

```bash
git add cc_extractor/patches/hide_ctrl_g.py cc_extractor/patches/_registry.py cc_extractor/variants/tweaks.py tests/patches/test_hide_ctrl_g.py
git commit -m "Migrate hide-ctrl-g-to-edit to per-file module"
```

---

## Task 14: Migrate suppress-line-numbers

**Files:**
- Create: `cc_extractor/patches/suppress_line_numbers.py`
- Modify: `cc_extractor/patches/_registry.py`
- Modify: `cc_extractor/variants/tweaks.py`
- Create: `tests/patches/test_suppress_line_numbers.py`

- [ ] **Step 1: Test**

Create `tests/patches/test_suppress_line_numbers.py`:

```python
import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.suppress_line_numbers import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("suppress-line-numbers")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert "return C}function next" in outcome.js


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l1(cli_js_real, version):
    outcome = PATCH.apply(cli_js_real(version), PatchContext(claude_version=version))
    assert outcome.status == "applied"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l2(cli_js_real, version, parse_js):
    outcome = PATCH.apply(cli_js_real(version), PatchContext(claude_version=version))
    parse_js(outcome.js)
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/python -m pytest tests/patches/test_suppress_line_numbers.py -v`
Expected: FAIL.

- [ ] **Step 3: Create module**

Create `cc_extractor/patches/suppress_line_numbers.py`:

```python
"""Suppress per-line line number prefixes in file-read output."""

import re

from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    sig = re.search(
        r"\{content:([$\w]+),startLine:[$\w]+\}\)\{if\(!\1\)return\"\";"
        r"let ([$\w]+)=\1\.split\([^)]+\);",
        js,
    )
    if sig:
        replace_start = sig.end()
        end = re.search(r"\}(?=function |var |let |const |[$\w]+=[$\w]+\()", js[replace_start:])
        if end:
            new_js = js[:replace_start] + f"return {sig.group(1)}" + js[replace_start + end.start():]
            return PatchOutcome(js=new_js, status="applied")

    arrow = re.search(
        r"if\(([$\w]+)\.length>=\d+\)return`\$\{\1\}(?:→|\\u2192)\$\{([$\w]+)\}`;"
        r"return`\$\{\1\.padStart\(\d+,\" \"\)\}(?:→|\\u2192)\$\{\2\}`",
        js,
    )
    if arrow:
        new_js = js[:arrow.start()] + f"return {arrow.group(2)}" + js[arrow.end():]
        return PatchOutcome(js=new_js, status="applied")
    return PatchOutcome(js=js, status="missed")


PATCH = Patch(
    id="suppress-line-numbers",
    name="Suppress line numbers in file reads",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
)
```

- [ ] **Step 4: Register, update shim, run, commit**

```bash
git add cc_extractor/patches/suppress_line_numbers.py cc_extractor/patches/_registry.py cc_extractor/variants/tweaks.py tests/patches/test_suppress_line_numbers.py
git commit -m "Migrate suppress-line-numbers to per-file module"
```

---

## Task 15: Migrate auto-accept-plan-mode

**Files:**
- Create: `cc_extractor/patches/auto_accept_plan_mode.py`
- Modify: `cc_extractor/patches/_registry.py`
- Modify: `cc_extractor/variants/tweaks.py`
- Create: `tests/patches/test_auto_accept_plan_mode.py`

- [ ] **Step 1: Test**

Create `tests/patches/test_auto_accept_plan_mode.py`:

```python
import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.auto_accept_plan_mode import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("auto-accept-plan-mode")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert 'onPick("yes-accept-edits");return null;return R.createElement' in outcome.js


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l1(cli_js_real, version):
    outcome = PATCH.apply(cli_js_real(version), PatchContext(claude_version=version))
    assert outcome.status == "applied"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l2(cli_js_real, version, parse_js):
    outcome = PATCH.apply(cli_js_real(version), PatchContext(claude_version=version))
    parse_js(outcome.js)
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/python -m pytest tests/patches/test_auto_accept_plan_mode.py -v`
Expected: FAIL.

- [ ] **Step 3: Create module**

Create `cc_extractor/patches/auto_accept_plan_mode.py`:

```python
"""Auto-accept the 'Ready to code?' plan-mode prompt."""

import re

from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    ready_idx = js.find('title:"Ready to code?"')
    if ready_idx == -1:
        return PatchOutcome(js=js, status="missed")
    if re.search(r"[$\w]+(?:\.current)?\(\"yes-accept-edits\"\);return null;return", js):
        return PatchOutcome(js=js, status="skipped")
    after = js[ready_idx:ready_idx + 3000]
    accept_func = None
    for pattern in (
        r"onChange:\([$\w]+\)=>([$\w]+)\([$\w]+\),onCancel",
        r"onChange:([$\w]+),onCancel",
        r"onChange:\([$\w]+\)=>void ([$\w]+)\.current\([$\w]+\),onCancel",
    ):
        match = re.search(pattern, after)
        if match:
            accept_func = match.group(1)
            if ".current" not in accept_func and "current" in pattern:
                accept_func += ".current"
            break
    if not accept_func:
        return PatchOutcome(js=js, status="missed")
    before_start = max(0, ready_idx - 500)
    before = js[before_start:ready_idx]
    return_idx = before.rfind("return ")
    if return_idx == -1:
        return PatchOutcome(js=js, status="missed")
    insert_at = before_start + return_idx
    insertion = f'{accept_func}("yes-accept-edits");return null;'
    new_js = js[:insert_at] + insertion + js[insert_at:]
    return PatchOutcome(js=new_js, status="applied")


PATCH = Patch(
    id="auto-accept-plan-mode",
    name="Auto-accept plan mode",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
)
```

- [ ] **Step 4: Register, update shim, run, commit**

```bash
git add cc_extractor/patches/auto_accept_plan_mode.py cc_extractor/patches/_registry.py cc_extractor/variants/tweaks.py tests/patches/test_auto_accept_plan_mode.py
git commit -m "Migrate auto-accept-plan-mode to per-file module"
```

---

## Task 16: Migrate allow-custom-agent-models

**Files:**
- Create: `cc_extractor/patches/allow_custom_agent_models.py`
- Modify: `cc_extractor/patches/_registry.py`
- Modify: `cc_extractor/variants/tweaks.py`
- Create: `tests/patches/test_allow_custom_agent_models.py`

- [ ] **Step 1: Test**

Create `tests/patches/test_allow_custom_agent_models.py`:

```python
import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.allow_custom_agent_models import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("allow-custom-agent-models")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert ",model:z.string().optional()" in outcome.js


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l1(cli_js_real, version):
    outcome = PATCH.apply(cli_js_real(version), PatchContext(claude_version=version))
    assert outcome.status == "applied"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l2(cli_js_real, version, parse_js):
    outcome = PATCH.apply(cli_js_real(version), PatchContext(claude_version=version))
    parse_js(outcome.js)
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/python -m pytest tests/patches/test_allow_custom_agent_models.py -v`
Expected: FAIL.

- [ ] **Step 3: Create module**

Create `cc_extractor/patches/allow_custom_agent_models.py`:

```python
"""Relax agent model validation to accept arbitrary string values."""

import re

from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    zod = re.search(r",model:([$\w]+)\.enum\(([$\w]+)\)\.optional\(\)", js)
    if not zod:
        loose = re.sub(
            r"(let\s+[$\w]+\s*=\s*([$\w]+)\s*&&\s*typeof\s+\2\s*===\"string\")"
            r"\s*&&\s*[$\w]+\.includes\(\2\)",
            r"\1",
            js,
            count=1,
        )
        if loose != js:
            return PatchOutcome(js=loose, status="applied")
        return PatchOutcome(js=js, status="missed")
    zod_var = zod.group(1)
    model_list_var = zod.group(2)
    new_js = js[:zod.start()] + f",model:{zod_var}.string().optional()" + js[zod.end():]
    pattern = re.compile(
        rf"([;)}}])let\s+([$\w]+)\s*=\s*([$\w]+)\s*&&\s*typeof\s+\3\s*===\"string\""
        rf"\s*&&\s*{re.escape(model_list_var)}\.includes\(\3\)"
    )
    valid = pattern.search(new_js)
    if not valid:
        return PatchOutcome(js=js, status="missed")
    replacement = (
        f'{valid.group(1)}let {valid.group(2)}={valid.group(3)}'
        f'&&typeof {valid.group(3)}==="string"'
    )
    new_js = new_js[:valid.start()] + replacement + new_js[valid.end():]
    return PatchOutcome(js=new_js, status="applied")


PATCH = Patch(
    id="allow-custom-agent-models",
    name="Allow custom agent models",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
)
```

- [ ] **Step 4: Register, update shim, run, commit**

```bash
git add cc_extractor/patches/allow_custom_agent_models.py cc_extractor/patches/_registry.py cc_extractor/variants/tweaks.py tests/patches/test_allow_custom_agent_models.py
git commit -m "Migrate allow-custom-agent-models to per-file module"
```

---

## Task 17: Migrate patches-applied-indication

**Files:**
- Create: `cc_extractor/patches/patches_applied_indication.py`
- Modify: `cc_extractor/patches/_registry.py`
- Modify: `cc_extractor/variants/tweaks.py`
- Create: `tests/patches/test_patches_applied_indication.py`

- [ ] **Step 1: Test**

Create `tests/patches/test_patches_applied_indication.py`:

```python
import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.patches_applied_indication import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("patches-applied-indication")
    outcome = PATCH.apply(
        js, PatchContext(claude_version=None, provider_label="Provider"),
    )
    assert outcome.status == "applied"
    assert "(Claude Code, Provider variant)" in outcome.js


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l1(cli_js_real, version):
    outcome = PATCH.apply(
        cli_js_real(version),
        PatchContext(claude_version=version, provider_label="Provider"),
    )
    assert outcome.status == "applied"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l2(cli_js_real, version, parse_js):
    outcome = PATCH.apply(
        cli_js_real(version),
        PatchContext(claude_version=version, provider_label="Provider"),
    )
    parse_js(outcome.js)
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/python -m pytest tests/patches/test_patches_applied_indication.py -v`
Expected: FAIL.

- [ ] **Step 3: Create module**

Create `cc_extractor/patches/patches_applied_indication.py`:

```python
"""Append the provider label to the (Claude Code) version banner."""

from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    marker = " (Claude Code)"
    idx = js.find(marker)
    if idx == -1:
        return PatchOutcome(js=js, status="missed")
    replacement = f" (Claude Code, {ctx.provider_label} variant)"
    new_js = js[:idx] + replacement + js[idx + len(marker):]
    return PatchOutcome(js=new_js, status="applied")


PATCH = Patch(
    id="patches-applied-indication",
    name="Patches-applied indication",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
)
```

- [ ] **Step 4: Register, update shim, run, commit**

```bash
git add cc_extractor/patches/patches_applied_indication.py cc_extractor/patches/_registry.py cc_extractor/variants/tweaks.py tests/patches/test_patches_applied_indication.py
git commit -m "Migrate patches-applied-indication to per-file module"
```

---

## Task 18: Migrate themes (adapter over binary_patcher.theme)

**Files:**
- Create: `cc_extractor/patches/themes.py`
- Modify: `cc_extractor/patches/_registry.py`
- Modify: `cc_extractor/variants/tweaks.py`
- Create: `tests/patches/test_themes.py`

- [ ] **Step 1: Test**

Create `tests/patches/test_themes.py`:

```python
import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.themes import PATCH
from tests.patches.conftest import resolve_tested_versions


THEMES = [
    {"id": "dark", "name": "Dark mode", "colors": {"bashBorder": "#fff"}},
    {"id": "provider", "name": "Provider", "colors": {"bashBorder": "#daa"}},
]


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("themes")
    outcome = PATCH.apply(
        js,
        PatchContext(
            claude_version=None,
            config={"settings": {"themes": THEMES}},
        ),
    )
    assert outcome.status == "applied"
    assert 'case"provider":return{"bashBorder":"#daa"}' in outcome.js


def test_skipped_when_no_themes_in_config(cli_js_synthetic):
    js = cli_js_synthetic("themes")
    outcome = PATCH.apply(js, PatchContext(claude_version=None, config={}))
    assert outcome.status == "skipped"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l1(cli_js_real, version):
    outcome = PATCH.apply(
        cli_js_real(version),
        PatchContext(
            claude_version=version,
            config={"settings": {"themes": THEMES}},
        ),
    )
    assert outcome.status == "applied"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l2(cli_js_real, version, parse_js):
    outcome = PATCH.apply(
        cli_js_real(version),
        PatchContext(
            claude_version=version,
            config={"settings": {"themes": THEMES}},
        ),
    )
    parse_js(outcome.js)
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/python -m pytest tests/patches/test_themes.py -v`
Expected: FAIL.

- [ ] **Step 3: Create module**

Create `cc_extractor/patches/themes.py`:

```python
"""Inject custom themes into Claude Code's theme registry.

Adapter over cc_extractor.binary_patcher.theme.
"""

from ..binary_patcher.theme import apply_theme, themes_from_config
from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    themes = themes_from_config(dict(ctx.config) if ctx.config else None)
    if not themes:
        return PatchOutcome(js=js, status="skipped")
    result = apply_theme(js, themes)
    if result.replaced:
        return PatchOutcome(js=result.js, status="applied")
    return PatchOutcome(js=result.js, status="skipped")


PATCH = Patch(
    id="themes",
    name="Custom themes",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
)
```

- [ ] **Step 4: Register, update shim**

In `_registry.py`, add import + entry. In `variants/tweaks.py`, the existing themes branch in `apply_variant_tweaks` is special-cased (calls `apply_theme` directly). Replace that branch with the registry-delegating branch the same way as Task 9 step 6 — the new branch handles config/themes the same.

Concretely, in `cc_extractor/variants/tweaks.py`, find:

```python
        if tweak_id == "themes":
            themed = apply_theme(js, _themes_from_config(config))
            js = themed.js
            if themed.replaced:
                applied.append(tweak_id)
            else:
                skipped.append(tweak_id)
```

Delete this whole block. The generic `elif tweak_id in _PATCH_REGISTRY:` block from Task 9 already handles it.

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/patches/test_themes.py tests/test_variant_tweaks.py tests/test_binary_patcher_theme.py -v`
Expected: All PASS. The existing `test_apply_variant_tweaks_applies_theme_prompt_and_indicator` continues to pass via the shim.

Run: `.venv/bin/python -m pytest -q`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add cc_extractor/patches/themes.py cc_extractor/patches/_registry.py cc_extractor/variants/tweaks.py tests/patches/test_themes.py
git commit -m "Migrate themes patch to per-file adapter"
```

---

## Task 19: Migrate prompt-overlays (adapter over binary_patcher.prompts)

**Files:**
- Create: `cc_extractor/patches/prompt_overlays.py`
- Modify: `cc_extractor/patches/_registry.py`
- Modify: `cc_extractor/variants/tweaks.py`
- Create: `tests/patches/test_prompt_overlays.py`

- [ ] **Step 1: Test**

Create `tests/patches/test_prompt_overlays.py`:

```python
import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.prompt_overlays import PATCH


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("prompt-overlays")
    outcome = PATCH.apply(
        js,
        PatchContext(claude_version=None, overlays={"webfetch": "Use provider docs."}),
    )
    assert outcome.status == "applied"
    assert "Use provider docs." in outcome.js


def test_unknown_overlay_recorded_as_note(cli_js_synthetic):
    js = cli_js_synthetic("prompt-overlays")
    outcome = PATCH.apply(
        js,
        PatchContext(claude_version=None, overlays={"nonexistent_target": "x"}),
    )
    # patch declares on_miss="warn" so unknown overlays do not fail; they
    # are recorded in notes
    assert outcome.status in ("applied", "skipped", "missed")
    assert any("nonexistent_target" in note for note in outcome.notes)


def test_skipped_when_no_overlays(cli_js_synthetic):
    js = cli_js_synthetic("prompt-overlays")
    outcome = PATCH.apply(js, PatchContext(claude_version=None, overlays={}))
    assert outcome.status == "skipped"


def test_metadata_uses_warn_on_miss():
    assert PATCH.on_miss == "warn"
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/python -m pytest tests/patches/test_prompt_overlays.py -v`
Expected: FAIL.

- [ ] **Step 3: Create module**

Create `cc_extractor/patches/prompt_overlays.py`:

```python
"""Inject provider overlay blocks after known prompt anchors.

Adapter over cc_extractor.binary_patcher.prompts.apply_prompts.
"""

from ..binary_patcher.prompts import apply_prompts
from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    overlays = dict(ctx.overlays) if ctx.overlays else {}
    if not overlays:
        return PatchOutcome(js=js, status="skipped")
    result = apply_prompts(js, overlays)
    notes = tuple(f"prompt overlay miss: {key}" for key in result.missing)
    if result.replaced_targets:
        return PatchOutcome(js=result.js, status="applied", notes=notes)
    return PatchOutcome(js=result.js, status="skipped", notes=notes)


PATCH = Patch(
    id="prompt-overlays",
    name="Prompt overlays",
    group="prompts",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    on_miss="warn",
    apply=_apply,
)
```

- [ ] **Step 4: Register; remove the special-case `prompt-overlays` branch in `variants/tweaks.py`** (same pattern as Task 18 step 4). Find the `elif tweak_id == "prompt-overlays":` block in `apply_variant_tweaks` and delete it.

The new shim path handles overlays via `PatchContext.overlays`. After this step there is no `_PATCHERS` entry for the migrated 11 ids, and `_PATCHERS` may be empty.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add cc_extractor/patches/prompt_overlays.py cc_extractor/patches/_registry.py cc_extractor/variants/tweaks.py tests/patches/test_prompt_overlays.py
git commit -m "Migrate prompt-overlays patch to per-file adapter"
```

---

## Task 20: Slim variants/tweaks.py to a thin shim

**Files:**
- Modify: `cc_extractor/variants/tweaks.py`

- [ ] **Step 1: Audit what `_PATCHERS` and the legacy `_*` functions still hold**

Run: `grep -n "_PATCHERS\|^def _" cc_extractor/variants/tweaks.py`
Expected: `_PATCHERS = {}` (or close to it) and all the `_show_more_items`, `_model_customizations`, etc. functions still defined as dead code.

- [ ] **Step 2: Delete the dead helper functions and the empty `_PATCHERS` dict**

Open `cc_extractor/variants/tweaks.py`. Remove every `def _<...>(...)` whose id is now in the registry: `_show_more_items`, `_model_customizations`, `_hide_startup_banner`, `_hide_startup_clawd`, `_hide_ctrl_g_to_edit`, `_suppress_line_numbers`, `_auto_accept_plan_mode`, `_allow_custom_agent_models`, `_patches_applied_indication`. Remove the now-empty `_PATCHERS = {}` and the `else: patcher = _PATCHERS[tweak_id]` branch in `apply_variant_tweaks`. The remaining loop body is just `if env_id: skip; elif registry: delegate`.

- [ ] **Step 3: Remove now-unused imports** at the top of `tweaks.py`. The only import paths still needed are `cc_extractor.patches`, `cc_extractor.patches._registry`, plus `dataclasses.dataclass`, `typing.*`, and basic stdlib. The imports of `apply_prompts`, `apply_theme`, `themes_from_config` can be deleted if no remaining code references them.

- [ ] **Step 4: Run the full test suite**

Run: `.venv/bin/python -m pytest -q`
Expected: All PASS, including `tests/test_variant_tweaks.py`.

- [ ] **Step 5: Confirm the shim is small**

Run: `wc -l cc_extractor/variants/tweaks.py`
Expected: under 80 lines.

- [ ] **Step 6: Commit**

```bash
git add cc_extractor/variants/tweaks.py
git commit -m "Slim variants/tweaks.py to thin registry-delegating shim"
```

---

## Task 21: claude_version plumbing through apply_variant_tweaks

**Files:**
- Modify: `cc_extractor/variants/tweaks.py`
- Modify: `cc_extractor/variants/__init__.py` (or wherever variant build calls into apply_variant_tweaks)
- Modify: `tests/test_variant_tweaks.py`

- [ ] **Step 1: Add a failing test that verifies the warning fires**

Append to `tests/test_variant_tweaks.py`:

```python
import warnings


def test_apply_variant_tweaks_warns_on_untested_version():
    js = ',R.createElement(B,{isBeforeFirstMessage:!1}),'
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        apply_variant_tweaks(
            js,
            tweak_ids=["hide-startup-banner"],
            claude_version="1.0.0",  # not in any tested range
            force=True,  # bypass unsupported-version error so we can observe the warning
        )
    assert any("1.0.0" in str(w.message) for w in caught)
```

- [ ] **Step 2: Run to confirm failure**

Run: `.venv/bin/python -m pytest tests/test_variant_tweaks.py::test_apply_variant_tweaks_warns_on_untested_version -v`
Expected: FAIL with `TypeError: unexpected keyword argument 'claude_version'` or similar.

- [ ] **Step 3: Add `claude_version` and `force` parameters to `apply_variant_tweaks`**

Edit the signature in `cc_extractor/variants/tweaks.py`:

```python
def apply_variant_tweaks(
    js: str,
    *,
    tweak_ids: Iterable[str],
    config: Optional[Dict] = None,
    overlays: Optional[Dict[str, str]] = None,
    provider_label: str = "cc-extractor",
    claude_version: Optional[str] = None,
    force: bool = False,
) -> TweakResult:
```

Forward `claude_version` and `force` into the `PatchContext` constructed inside the loop.

- [ ] **Step 4: Plumb `claude_version` from the variant build path**

Locate the call site in `cc_extractor/variants/__init__.py` (or a builder module). Pass `claude_version=manifest_version` (or whatever the manifest field is called — grep for `"claude_version"`/`"version"` in `variants/`). If the call site does not have a version handy, leave it as `None` (preserves current behavior).

Run: `grep -rn "apply_variant_tweaks" cc_extractor/`
Expected: 1-3 call sites; update each.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: All PASS, new warning test included.

- [ ] **Step 6: Commit**

```bash
git add cc_extractor/variants/tweaks.py cc_extractor/variants/__init__.py tests/test_variant_tweaks.py
git commit -m "Plumb claude_version through apply_variant_tweaks"
```

---

## Task 22: L3 smoke harness

**Files:**
- Create: `tests/patches_smoke/__init__.py`
- Create: `tests/patches_smoke/test_variant_smoke.py`

- [ ] **Step 1: Create empty package**

Create `tests/patches_smoke/__init__.py` (empty).

- [ ] **Step 2: Write the gated smoke test**

Create `tests/patches_smoke/test_variant_smoke.py`:

```python
"""L3 smoke: build a default-tweak variant against each resolved version
and verify the resulting binary boots cleanly.

Gated: skipped unless CC_EXTRACTOR_REAL_BINARY=1.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from cc_extractor.download_index import load_download_index
from cc_extractor.patches._versions import resolve_range_to_version
from tests.patches._pinned import DEFAULT_VERSION_RANGES


pytestmark = pytest.mark.skipif(
    os.environ.get("CC_EXTRACTOR_REAL_BINARY") != "1",
    reason="CC_EXTRACTOR_REAL_BINARY=1 not set",
)


def _resolved_versions():
    index = load_download_index()
    out = []
    for range_expr in DEFAULT_VERSION_RANGES:
        version = resolve_range_to_version(range_expr, index=index)
        if version is not None and version not in out:
            out.append(version)
    return out


@pytest.mark.parametrize("version", _resolved_versions())
def test_variant_boots(version, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = {**os.environ, "CC_EXTRACTOR_WORKSPACE": str(workspace)}

    cmd = [
        ".venv/bin/python",
        "main.py",
        "variant",
        "create",
        f"smoke-{version.replace('.', '-')}",
        "--claude-version",
        version,
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, f"variant create failed: {proc.stderr}"

    run_cmd = [
        ".venv/bin/python", "main.py", "variant", "run",
        f"smoke-{version.replace('.', '-')}", "--", "--version",
    ]
    proc = subprocess.run(run_cmd, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"variant run failed: {proc.stderr}"
    # Claude Code prints its version on `--version`; assert non-empty stdout.
    assert proc.stdout.strip(), "expected version output, got empty stdout"
```

- [ ] **Step 3: Verify it skips by default**

Run: `.venv/bin/python -m pytest tests/patches_smoke -v`
Expected: All tests SKIPPED with reason "CC_EXTRACTOR_REAL_BINARY=1 not set".

- [ ] **Step 4: Manually run the gated smoke once to verify it works**

Run: `CC_EXTRACTOR_REAL_BINARY=1 .venv/bin/python -m pytest tests/patches_smoke -v`
Expected: PASS for at least one resolved version (or SKIP if `--claude-version` is not a recognized variant CLI flag — in which case adjust the cmd to whatever the CLI takes).

- [ ] **Step 5: Commit**

```bash
git add tests/patches_smoke/
git commit -m "Add L3 smoke test: build variant, boot binary, gated"
```

---

## Task 23: L4 harness skeleton + first snapshot test

**Files:**
- Create: `tests/patches_behavioral/__init__.py`
- Create: `tests/patches_behavioral/conftest.py`
- Create: `tests/patches_behavioral/test_hide_startup_banner_snapshot.py`

- [ ] **Step 1: Create the gating + variant fixture skeleton**

Create `tests/patches_behavioral/__init__.py` (empty).

Create `tests/patches_behavioral/conftest.py`:

```python
"""L4 fixtures: build/run/teardown one variant per test.

Gated: every test in this directory skips unless CC_EXTRACTOR_TUI_MCP=1.
The TUI MCP itself is not invoked from Python here; instead, this conftest
is a thin shell that prepares variants. The actual screen capture and
snapshot diff happen in test bodies (which call into the MCP via whatever
mechanism the executing harness provides — see docs/patches.md).
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("CC_EXTRACTOR_TUI_MCP") != "1",
    reason="CC_EXTRACTOR_TUI_MCP=1 not set",
)


@pytest.fixture
def variant_factory(tmp_path):
    """Returns a function that builds a fresh variant in a per-test workspace
    and returns its run command (list[str]). Variants are torn down by
    pytest's tmp_path cleanup."""

    def build(name: str, claude_version: str, tweak_ids):
        workspace = tmp_path / "workspace"
        workspace.mkdir(exist_ok=True)
        env = {**os.environ, "CC_EXTRACTOR_WORKSPACE": str(workspace)}
        cmd = [
            ".venv/bin/python", "main.py", "variant", "create", name,
            "--claude-version", claude_version,
        ] + [arg for tweak in tweak_ids for arg in ("--tweak", tweak)]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            pytest.skip(f"variant create failed: {proc.stderr}")
        return [".venv/bin/python", "main.py", "variant", "run", name, "--"], env
    return build


SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
SNAPSHOT_DIR.mkdir(exist_ok=True)


def assert_snapshot(actual: str, snapshot_name: str) -> None:
    """Compare `actual` to snapshots/<snapshot_name>.txt. Update with
    CC_EXTRACTOR_UPDATE_SNAPSHOTS=1."""
    path = SNAPSHOT_DIR / f"{snapshot_name}.txt"
    if os.environ.get("CC_EXTRACTOR_UPDATE_SNAPSHOTS") == "1":
        path.write_text(actual)
        return
    if not path.exists():
        path.write_text(actual)
        pytest.skip(f"snapshot created: {path}")
    expected = path.read_text()
    assert actual == expected, f"snapshot mismatch for {snapshot_name}"
```

- [ ] **Step 2: Add a placeholder behavioral test for hide-startup-banner**

Create `tests/patches_behavioral/test_hide_startup_banner_snapshot.py`:

```python
"""Placeholder L4 snapshot test for hide-startup-banner.

The test body captures the variant's startup screen (via whatever TUI
capture mechanism the executing harness supplies) and asserts the result
matches snapshots/hide_startup_banner.txt. The actual capture call
depends on the TUI MCP integration; this skeleton exists so the harness
shape is exercised without committing to a specific MCP API yet.
"""

import os

import pytest

from tests.patches_behavioral.conftest import assert_snapshot


pytestmark = pytest.mark.skipif(
    os.environ.get("CC_EXTRACTOR_TUI_MCP") != "1",
    reason="CC_EXTRACTOR_TUI_MCP=1 not set",
)


def test_banner_hidden(variant_factory):
    cmd, env = variant_factory(
        "smoke-banner",
        claude_version="2.1.123",  # adjust to a version present in the index
        tweak_ids=["hide-startup-banner"],
    )
    pytest.skip(
        "L4 capture mechanism not wired up yet; this test is a skeleton. "
        "Wire to TUI MCP in a follow-up; for now assert_snapshot is unused."
    )
    # Future:
    # screen = capture_via_tui_mcp(cmd, env, settle_timeout=3.0)
    # assert_snapshot(screen, "hide_startup_banner")
```

- [ ] **Step 3: Verify it skips by default**

Run: `.venv/bin/python -m pytest tests/patches_behavioral -v`
Expected: SKIPPED with "CC_EXTRACTOR_TUI_MCP=1 not set".

- [ ] **Step 4: Commit**

```bash
git add tests/patches_behavioral/
git commit -m "Add L4 behavioral test scaffold and first snapshot skeleton"
```

---

## Task 24: Documentation

**Files:**
- Create: `docs/patches.md`

- [ ] **Step 1: Write the patch authoring guide**

Create `docs/patches.md`:

```markdown
# Patches

Patches rewrite Claude Code's bundled JS to add custom behavior. Each
patch lives in `cc_extractor/patches/<id>.py` and is registered in
`cc_extractor/patches/_registry.py`.

## Authoring a new patch

1. Find the upstream tweakcc patch in `vendor/tweakcc/src/patches/<name>.ts`.
2. Create `cc_extractor/patches/<id>.py` with a `_apply(js, ctx)` function
   and a `PATCH = Patch(...)` constant. Mirror the regex shape from the
   tweakcc TS file. Use `[$\w]+` not `\w+` for identifiers.
3. Add a synthetic snippet for `<id>` to `tests/patches/fixtures/synthetic.py`.
4. Add `tests/patches/test_<id>.py` covering synthetic + real fixtures.
5. Register in `cc_extractor/patches/_registry.py`.
6. Run `pytest -q tests/patches/test_<id>.py` until green.

## Patch metadata fields

| Field | Type | Purpose |
|---|---|---|
| `id` | str | Stable kebab-case identifier |
| `name` | str | Human-readable label |
| `group` | str | One of: ui, thinking, prompts, tools, system |
| `versions_supported` | SemVer range | Versions where the patch is allowed |
| `versions_tested` | tuple of SemVer ranges | Each entry = one test matrix bucket |
| `versions_blacklisted` | tuple of exact versions | Known-broken versions |
| `on_miss` | "fatal" \| "skip" \| "warn" | What happens if anchor not found |
| `apply` | callable | `(js, ctx) -> PatchOutcome` |

## Test tiers

- **L1 (anchor):** regex matches expected pattern. Run via `pytest tests/patches/`.
- **L2 (parse):** patched JS parses cleanly under `node --check`. Same command; skipped if Node missing.
- **L3 (boot smoke):** built variant binary boots and exits cleanly.
  Run with `CC_EXTRACTOR_REAL_BINARY=1 pytest tests/patches_smoke/`.
- **L4 (behavioral):** TUI MCP drives the variant, screen state captured
  and diffed against snapshots.
  Run with `CC_EXTRACTOR_TUI_MCP=1 pytest tests/patches_behavioral/`.

## Updating L4 snapshots

```bash
CC_EXTRACTOR_TUI_MCP=1 CC_EXTRACTOR_UPDATE_SNAPSHOTS=1 \
  pytest tests/patches_behavioral/test_<id>_snapshot.py
```

## Running everything

```bash
CC_EXTRACTOR_REAL_BINARY=1 CC_EXTRACTOR_TUI_MCP=1 \
  .venv/bin/python -m pytest -q
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/patches.md
git commit -m "Document patch authoring workflow and test tiers"
```

---

## Task 25: Final verification pass

**Files:** none

- [ ] **Step 1: Run the full default suite**

Run: `.venv/bin/python -m pytest -q`
Expected: All PASS, no warnings about deprecated APIs, no SKIPPED beyond expected (Node-missing on minimal envs).

- [ ] **Step 2: Run gated suites**

Run: `CC_EXTRACTOR_REAL_BINARY=1 .venv/bin/python -m pytest -q tests/patches_smoke/`
Expected: PASS or clear SKIP messages.

Run: `CC_EXTRACTOR_TUI_MCP=1 .venv/bin/python -m pytest -q tests/patches_behavioral/`
Expected: PASS (snapshot skeleton skips intentionally; that is acceptable for this milestone).

- [ ] **Step 3: Verify the shim is small**

Run: `wc -l cc_extractor/variants/tweaks.py`
Expected: under 80 lines.

- [ ] **Step 4: Verify all 11 tweaks live in patches/**

Run: `ls cc_extractor/patches/*.py | grep -v "^cc_extractor/patches/_" | grep -v "system_prompts" | wc -l`
Expected: 11 (themes, prompt_overlays, hide_startup_banner, hide_startup_clawd, hide_ctrl_g, show_more_items, model_customizations, suppress_line_numbers, auto_accept_plan_mode, allow_custom_agent_models, patches_applied_indication).

- [ ] **Step 5: Open a final review commit (no-op if nothing changed)**

If anything got fixed during verification, commit it. Otherwise, this task ends without a new commit.

---

## Deferred (in spec, not in this plan)

- **`--patches-report <path>` CLI flag** on `apply-binary` and `variant create` (spec §Observability). Marked optional/off-by-default in the spec; implement in a follow-up plan once the framework lands. Implementing now would mean threading `AggregateResult` plumbing through the CLI handler layer that this plan otherwise leaves untouched.
- **Behavioral L4 wiring** beyond the harness skeleton in Task 23. The skeleton exercises the variant-build path and the snapshot helpers; actual TUI MCP capture for each patch is a follow-up plan, one snapshot at a time.
