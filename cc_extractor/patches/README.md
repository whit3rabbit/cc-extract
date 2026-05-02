# Patch Authoring Guide

This package contains the regex-tweak patch layer for Claude Code entry JS.
The broader workflow and test-tier definitions live in
[docs/patches.md](../../docs/patches.md). Keep this README focused on local
format, registration, and review rules for files in `cc_extractor/patches/`.

This is separate from `cc_extractor.binary_patcher`, which handles workspace
patch packages and binary-level operations.

## When To Add A Patch

Add a Python patch here when the change can be expressed as a small, versioned
rewrite of bundled entry JS.

Prefer deferring the patch when it needs:

- a new settings model or TUI controls,
- user-global configuration writes,
- broad behavior changes that are hard to test from fixtures,
- safety bypasses such as sudo/root permission guard removal.

## File Layout

Use one module per patch ID:

```text
cc_extractor/patches/<snake_name>.py
tests/patches/test_<snake_name>.py
tests/patches/fixtures/synthetic.py
```

Patch IDs are stable kebab-case strings. Module filenames are snake_case.

## Patch Template

```python
"""Short behavior summary."""

import re

from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    match = re.search(r"anchor with [$\w]+ identifiers", js)
    if not match:
        return PatchOutcome(js=js, status="missed")

    replacement = "..."
    new_js = js[:match.start()] + replacement + js[match.end():]
    return PatchOutcome(js=new_js, status="applied")


PATCH = Patch(
    id="patch-id",
    name="Patch label",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
    description="One sentence user-facing description.",
)
```

Valid groups are `ui`, `thinking`, `prompts`, `tools`, and `system`.

Use `PatchOutcome` statuses consistently:

- `applied`: JS changed and should be forwarded.
- `skipped`: anchor absence or config means no change is needed.
- `missed`: expected anchor was not found and should fail unless `on_miss`
  says otherwise.

Most patches should keep the default `on_miss="fatal"`. Use `skip` or `warn`
only when anchor absence is expected and safe, and include a note when useful.

## Regex Rules

- Start from the upstream tweakcc implementation when one exists:
  `vendor/tweakcc/src/patches/<name>.ts`.
- Match minified identifiers with `[$\w]+`, not `\w+`.
- Keep regex windows as narrow as practical. Avoid matching across unrelated
  functions unless the upstream bundle shape requires it.
- Prefer structured captures and slice replacement over broad global string
  replacement.
- Preserve syntax around commas, semicolons, and expression boundaries.
- Keep generated code minified-style if it is inserted into minified JS.
- Do not silently hard-code config-heavy behavior. Read values from
  `ctx.config` only when the patch already has a stable config shape.

## Version Rules

- Set `versions_supported` to the broad range where the patch is allowed.
- Set `versions_tested` only to ranges verified by real fixture tests.
- Narrow support when real L1 anchors fail. Do not claim support from a
  synthetic fixture alone.
- `versions_tested` must be a subset of `versions_supported`; registry tests
  enforce this. Avoid exact duplicate open-ended ranges such as
  `versions_supported=">=2.1.0,<2.1.42"` and
  `versions_tested=(">=2.1.0,<2.1.42",)` because endpoint checks can fail.
  Use a concrete inclusive upper endpoint such as `<=2.1.41` when needed.
- Add `versions_blacklisted` only for exact versions known to be broken.

## Registration Checklist

1. Add `cc_extractor/patches/<snake_name>.py`.
2. Add the module import and `PATCH` entry in
   `cc_extractor/patches/_registry.py`.
3. Add a synthetic fixture under `SYNTHETIC["patch-id"]`.
4. Add `tests/patches/test_<snake_name>.py`.
5. If the patch should be user-selectable, add it to
   `CURATED_TWEAK_IDS` in `cc_extractor/variants/tweaks.py`.
6. If it is safe for one-click dashboard use on current versions, make sure it
   is not in `DASHBOARD_EXCLUDED_TWEAK_IDS`.
7. Update TUI or variant tests when visible IDs change.

## TUI Visibility

There is no separate TUI patch registry.

The setup wizard's Tweaks step auto-populates from `CURATED_TWEAK_IDS` in
`cc_extractor/variants/tweaks.py`. Add the patch ID there when users should be
able to select it for variants.

The Dashboard Patches step auto-populates from `DASHBOARD_TWEAK_IDS`, which is
derived from `CURATED_TWEAK_IDS` minus `DASHBOARD_EXCLUDED_TWEAK_IDS`. The TUI
then filters that list against `cc_extractor.patches._registry.REGISTRY`, so a
dashboard-visible patch must be both registered and not excluded.

Use `DASHBOARD_EXCLUDED_TWEAK_IDS` for patches that are curated but should not
be available as one-click dashboard choices, such as env-backed tweaks,
version-bounded legacy patches, prompt overlays, or patches that need config UI.

When changing either list, update `tests/test_variant_tweaks.py` and
`tests/test_tui.py` to prove the expected visibility.

## Test Template

```python
import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.patch_module import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("patch-id")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert "expected change" in outcome.js


def test_metadata():
    assert PATCH.id == "patch-id"
    assert PATCH.group == "ui"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l1(cli_js_real, version):
    outcome = PATCH.apply(cli_js_real(version), PatchContext(claude_version=version))
    assert outcome.status == "applied"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l2(cli_js_real, version, parse_js):
    js = cli_js_real(version)
    try:
        parse_js(js)
    except AssertionError:
        pytest.skip(f"original extracted JS for {version} does not parse; skipping L2 test")
    outcome = PATCH.apply(js, PatchContext(claude_version=version))
    parse_js(outcome.js)
```

If a patch intentionally skips on some versions, assert the explicit allowed
statuses and document why in the test.

## Required Verification

For a new patch, run:

```bash
rtk .venv/bin/python -m pytest -q \
  tests/patches/test_<snake_name>.py \
  tests/patches/test_registry.py
```

When curated or dashboard-visible IDs change, also run:

```bash
rtk .venv/bin/python -m pytest -q tests/test_variant_tweaks.py tests/test_tui.py
```

Run Ruff on touched Python surfaces:

```bash
rtk ruff check cc_extractor/patches tests/patches
```

For terminal-visible behavior, add or update gated behavioral tests under
`tests/patches_behavioral/` and verify with `CC_EXTRACTOR_TUI_MCP=1`.
Use one key per TUI MCP call, for example `Down`, `Up`, `Enter`, `Space`,
or `q`.

## Review Notes

- Keep vendor `vendor/tweakcc` read-only unless explicitly asked.
- Do not port `allow-sudo-bypass-permissions` without explicit approval.
- Do not add dependencies for a patch without approval.
- Keep patch code small and reversible. If a regex becomes too broad to
  explain, narrow the version range or defer the patch.
