# AGENTS.md

This directory contains the regex-tweak patch layer. Read
[../../docs/patches.md](../../docs/patches.md) before changing patch behavior.
Use this file for directory-local rules that apply to every patch module and
patch test.

## Scope

- Patch modules live in `cc_extractor/patches/<snake_name>.py`.
- Each patch exposes exactly one `PATCH = Patch(...)`, unless the module is a
  deliberate small family such as MCP startup patches.
- Register every patch in `_registry.py`.
- This directory is not the workspace patch-package system. Do not mix it with
  `cc_extractor.binary_patcher`.

## Patch Format

- Use `_apply(js: str, ctx: PatchContext) -> PatchOutcome`.
- Return `PatchOutcome(js=new_js, status="applied")` only after changing JS.
- Return `status="missed"` when an expected anchor is absent.
- Return `status="skipped"` only when no-op behavior is expected and safe.
- Keep metadata complete: `id`, `name`, `group`, `versions_supported`,
  `versions_tested`, `apply`, and `description`.
- Valid groups: `ui`, `thinking`, `prompts`, `tools`, `system`.

## Regex Rules

- Mirror tweakcc regex shape from `vendor/tweakcc/src/patches/` when porting.
- Match minified identifiers with `[$\w]+`.
- Keep anchors narrow and explainable.
- Prefer slice replacement using match offsets.
- Preserve JavaScript syntax exactly around inserted or removed text.
- Do not use broad global replacement unless the upstream patch intentionally
  does and tests cover it.

## Version Rules

- Real L1 fixture tests define what is tested. Synthetic tests are not enough.
- Narrow `versions_supported` or `versions_tested` when real anchors fail.
- Keep `versions_tested` inside `versions_supported`; registry tests enforce
  this and endpoint behavior is strict.
- Use `versions_blacklisted` for exact broken versions only.

## Adding A Patch

1. Add the patch module.
2. Add a synthetic snippet in `tests/patches/fixtures/synthetic.py`.
3. Add `tests/patches/test_<snake_name>.py` with synthetic, metadata, L1, and
   L2 coverage.
4. Register the patch in `_registry.py`.
5. Add the ID to `CURATED_TWEAK_IDS` only when users should be able to select
   it.
6. Expose it in dashboard only when it is safe on current versions without new
   config UI.

## TUI Visibility

- There is no separate TUI registry for regex tweaks.
- The setup wizard Tweaks step reads `CURATED_TWEAK_IDS`.
- The Dashboard Patches step reads `DASHBOARD_TWEAK_IDS`, which is generated
  from `CURATED_TWEAK_IDS` minus `DASHBOARD_EXCLUDED_TWEAK_IDS`, then filtered
  against `_registry.REGISTRY`.
- Registering a patch in `_registry.py` is required for patching, but it does
  not make the patch user-selectable.
- Add curated patches that should not be dashboard one-click options to
  `DASHBOARD_EXCLUDED_TWEAK_IDS`.
- Update `tests/test_variant_tweaks.py` and `tests/test_tui.py` when visibility
  changes.

## Required Checks

For patch changes, run at minimum:

```bash
rtk .venv/bin/python -m pytest -q tests/patches/test_<snake_name>.py tests/patches/test_registry.py
rtk ruff check cc_extractor/patches tests/patches
```

For curated or dashboard list changes, also run:

```bash
rtk .venv/bin/python -m pytest -q tests/test_variant_tweaks.py tests/test_tui.py
```

For terminal-visible behavior, add gated L4 tests under
`tests/patches_behavioral/` and verify with `CC_EXTRACTOR_TUI_MCP=1`.

## Safety

- Do not modify `vendor/tweakcc` unless explicitly requested.
- Do not port `allow-sudo-bypass-permissions` without explicit approval.
- Do not add runtime dependencies for a patch without approval.
- Defer config-heavy patches until the config and TUI surface are designed.
