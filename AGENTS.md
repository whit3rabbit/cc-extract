# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

A standalone Python toolkit for extracting, patching, and repacking Bun standalone bundles inside Claude Code binaries. Used for research and educational purposes.

## Commands

```bash
# Install
.venv/bin/python -m pip install -e .
.venv/bin/python -m pip install -e '.[dev]'

# Run commands
.venv/bin/python main.py download [version]
.venv/bin/python main.py download --latest
.venv/bin/python main.py download --npm [version]
.venv/bin/python main.py inspect <binary> --json
.venv/bin/python main.py extract <binary> <dir>
.venv/bin/python main.py unpack <binary> --out <dir>
.venv/bin/python main.py replace-entry <binary> <entry-js> --out <binary>
.venv/bin/python main.py apply-binary <binary> --config <config.json> [--overlays <overlays.json>]
.venv/bin/python main.py pack <dir> <base> <out>
.venv/bin/python -m cc_extractor  # opens the TUI when attached to a TTY
.venv/bin/python -m pytest -q

# Lint
ruff check cc_extractor/ tools/ main.py
ruff check --fix cc_extractor/ tools/ main.py  # autofix

# Variants (isolated, named patched Claude Code installs)
.venv/bin/python main.py variant providers
.venv/bin/python main.py variant create <name> [--provider <key>] [--tweak <id> ...] [--claude-version <v>]
.venv/bin/python main.py variant list
.venv/bin/python main.py variant show <name>
.venv/bin/python main.py variant apply <name> [--claude-version <v>]
.venv/bin/python main.py variant update [<name> | --all] [--claude-version <v>]
.venv/bin/python main.py variant remove <name> [--yes]
.venv/bin/python main.py variant doctor [<name> | --all]
.venv/bin/python main.py variant run <name> -- [args...]

# Prompt extraction
.venv/bin/python tools/prompt_extractor.py <entry-js> --output prompts/<version>.json --version-hint <version>
.venv/bin/python tools/extract_prompt_versions.py --local
.venv/bin/python tools/extract_prompt_versions.py --versions 2.1.123 2.1.122 --force-prompts
.venv/bin/python tools/extract_prompt_versions.py --all --force-prompts
```

## Architecture

```text
main.py / __main__.py        -> CLI entry; `cmd_variant` dispatcher + `main()` (kept thin so tests can monkey-patch variant helpers via `cc_extractor.__main__`)
cli/parsers.py               -> Argparse parser tree (build_parser)
cli/handlers.py              -> Per-subcommand handlers (download/extract/inspect/replace-entry/apply-binary/pack/patch) + inspect_binary
cli/payloads.py              -> JSON payload helpers + variant arg adders
_utils.py                    -> Shared low-level helpers (safe_read_json, version_sort_key, utc_now, make_kebab_id); stdlib-only, no internal deps
tui/__init__.py              -> Action layer: run_tui, dispatchers, monkey-patchable hooks (apply_patch_packages_to_native, create_variant, doctor_variant, _variant_accepts_name_text)
tui/state.py, themes.py, options.py, rendering.py, dashboard.py, variant_actions.py, keys.py, nav.py, _runtime.py, _const.py
workspace/__init__.py        -> Re-exports everything; submodules paths.py, models.py, artifacts.py, patches.py, settings.py
downloader.py                -> Fetches binaries from Google Cloud Storage or NPM tarballs
download_index.py            -> Cached live/seed download version index
download_picker.py           -> Interactive version picker
bun_extract/parser.py        -> Shared Bun binary parser for Mach-O, ELF, and PE
bun_extract/extract.py       -> Writes extracted module files and `.bundle_manifest.json`
bun_extract/replace.py       -> Same-size in-place module replacement
binary_patcher/replace_entry.py -> Resize-capable entry JS replacement
binary_patcher/repack.py     -> Repack dispatcher for ELF, Mach-O, and PE
binary_patcher/*_resize.py   -> Platform-specific resize logic
binary_patcher/theme.py      -> Theme anchor patching + `themes_from_config` helper (canonical, was duplicated 3x before)
binary_patcher/prompts.py    -> Prompt overlay patching
binary_patcher/index.py      -> Structured apply_patches API (workspace patch packages; distinct from cc_extractor.patches.apply_patches which is the regex-tweak layer)
binary_patcher/codesign.py   -> Soft macOS ad-hoc signing helper
binary_patcher/js_patch.py   -> Patch extracted entry JS
binary_patcher/unpack_and_patch.py -> Unpacked Node fallback path
patches/__init__.py          -> Patch dataclass, PatchContext, PatchOutcome, AggregateResult, apply_patches (regex-tweak layer)
patches/_registry.py         -> Explicit REGISTRY: dict[str, Patch] keyed by patch id
patches/_versions.py         -> SemVer range parser, version_in_range, resolve_range_to_version
patches/_pinned_default.py   -> DEFAULT_VERSION_RANGES used by per-patch versions_tested
patches/<patch-id>.py        -> Per-file patch modules (themes, prompt_overlays, hide_startup_banner, etc.); each exposes PATCH = Patch(...)
patch_workflow.py            -> Extract, apply patch packages, repack, and write patched metadata
variants/__init__.py         -> Action layer: lifecycle (create/apply/update/remove/doctor/run) + `_build_variant_from_manifest`, `_copy_patch_or_unpack_variant_binary`, `_unpack_node_runtime_variant`, `_download_source_artifact` (monkey-patched targets stay alongside callers)
variants/model.py, builder.py, tweaks.py, wrapper.py
variants/tweaks.py           -> Thin shim: delegates to cc_extractor.patches.apply_patches; preserves TweakResult, TweakPatchError, apply_variant_tweaks public API
variant_tweaks.py            -> Backwards-compat shim re-exporting `cc_extractor.variants.tweaks`
providers.py                 -> Provider templates (Kimi, MiniMax, Z.AI, OpenRouter, Vercel, Ollama, NanoGPT) and env builders
extractor.py                 -> Compatibility wrapper over bun_extract
bundler.py                   -> Compatibility wrapper over binary_patcher.repack_binary
patcher.py                   -> Legacy extracted-text patch manifests
tools/prompt_extractor.py    -> Tree-sitter prompt extractor that writes tweakcc-style JSON
tools/extract_prompt_versions.py -> Download, extract, write, and validate prompt JSON files
prompts/*.json               -> Generated prompt catalogs keyed by Claude Code version
```

## Behavior Notes

- `parse_bun_binary` is the single source of truth for binary layout.
- `extractor.py` and `bundler.py` are compatibility layers, not independent parsers.
- `patcher.py` is only for old extracted-text patch manifests (still live: powers `patch apply`/`patch init` CLI plus `variants` and `patch_workflow`). Keep it separate from `binary_patcher`.
- Action layer stays in `tui/__init__.py` and `variants/__init__.py`: tests do `monkeypatch.setattr(tui, "create_variant", fake)` and `monkeypatch.setattr(variants_module, "_download_source_artifact", ...)`; patched name and call site must share the package's `__init__.py` globals. Pure helpers (rendering, options, builder utilities) belong in submodules.
- `tests/test_downloader.py` uses `@patch("cc_extractor.downloader.X")` string paths; do not move `downloader.py` into a subpackage without updating ~35 patch decorators.
- `cc_extractor/_utils.py` is the canonical home for cross-module helpers (`safe_read_json`, `version_sort_key`, `utc_now`, `make_kebab_id`); stdlib-only so any module can import it without circular risk.
- The TUI opens Dashboard first, then keeps Inspect, Extract, and Patch as advanced tabs.
- Dashboard v1 handles native binaries only. NPM downloads remain CLI-only.
- Dashboard profiles are workspace-local JSON files under `.cc-extractor/patches/profiles/<profile-id>.json`.
- Profile schema v1 uses `schemaVersion`, `id`, `name`, `patches` as `{id, version}` pairs, `createdAt`, and `updatedAt`.
- Profile names are UI/metadata only. Patched artifact paths still use deterministic patchset slugs.
- Profiles that reference missing patch packages are invalid for runs until corrected.
- Prompt anchor misses are recorded and non-fatal.
- Prompt extraction output belongs in `prompts/<version>.json`.
- Prompt extraction should preserve tweakcc-compatible JSON shape: top-level `version` and `prompts`, with each prompt carrying stable metadata when available.
- When available, use `vendor/tweakcc/data/prompts/prompts-<version>.json` as the comparison catalog for names, descriptions, identifiers, and short prompt recovery.
- Prompt JSON files must be validated after generation. Prefer `tools/extract_prompt_versions.py`, which validates before and after writing.
- `tools/extract_prompt_versions.py --all` is resumable but large. Prefer `--local` or explicit `--versions` unless intentionally backfilling all available Bun versions.
- Theme anchor misses are fatal structured failures.
- Mach-O signing is explicit and soft-failing through `codesign.py`.
- Unpacked fallback helpers support Python `.bundle_manifest.json` and TS-style `manifest.json`.
- Variants live under the workspace and are addressable by name or id; `variant_id_from_name` derives the slug.
- `variant_tweaks.DEFAULT_TWEAK_IDS` is the baseline applied on create. `ENV_TWEAK_IDS` are runtime env vars; the rest patch the binary.
- Provider templates in `providers.py` distinguish `auth_mode`, `requires_model_mapping`, and `no_prompt_pack`. Use `build_provider_env` rather than constructing env dicts ad hoc.
- `validate_variant_manifest` is the single source of truth for variant manifest shape; do not bypass it.
- Bun module bytes live at `data[info.data_start + module.cont_off : info.data_start + module.cont_off + module.cont_len]`. Field names are `cont_off`/`cont_len`, not `data_offset`/`data_size`.
- Bun entry module name varies by version: 2.0.x uses `claude`, 2.1.x uses `cli.js`. Use `info.entry_point_id` to find the entry; do not match by name suffix.
- `cc_extractor.downloader.download_binary(version, out_dir=None)` returns the local path string. There is no `download_native_binary`.
- Bun-bundled cli.js does not parse standalone under `node --check` (uses `bun:` imports). L2 parse tests must pre-check the unpatched JS and skip if it does not parse.
- `cc_extractor.patches.apply_patches` (regex tweaks) is separate from `cc_extractor.binary_patcher.index.apply_patches` (workspace patch packages). Do not confuse them.
- `range_contains_range` checks endpoint versions, so an inner range `<3` against an outer `<3` fails because `3.0.0` does not satisfy `<3`. Patches default to `<2.2` in versions_tested as a workaround.

## Development Notes

- Use `.venv/bin/python` for Python commands from the repository root.
- Linter: `ruff` (installed via Homebrew, not in venv). No `ruff.toml` config; defaults only. `tui/__init__.py` uses `__all__` for re-export suppression.
- Tests use `pytest`.
- Prompt extractor tests live under `tests/`.
- Prompt extraction dev dependencies include `tree-sitter` and `tree-sitter-javascript`.
- Runtime dependencies: `ratatui`, `tqdm`.
- Python 3.8+.
- No extra runtime dependency is required for P5. The unpacked fallback shells out to `npm` only when that helper is used.
- For TUI changes, add widget-independent state tests and smoke test with the TUI MCP using a temporary `CC_EXTRACTOR_WORKSPACE`.
- In TUI MCP smoke tests, prefer `Tab`, `Enter`, `Space`, text input, and `q`; verify arrow-key names before relying on them.
- Do not stage or commit submodule changes, including `vendor/tweakcc`, unless explicitly requested.
- Patch test tiers: L1 (anchor) + L2 (`node --check`) run by default under `pytest -q tests/patches/`. L3 (boot smoke) gated by `CC_EXTRACTOR_REAL_BINARY=1`. L4 (TUI MCP behavioral) gated by `CC_EXTRACTOR_TUI_MCP=1`. See `docs/patches.md`.
- Worktree convention: `.worktrees/<branch-name>` (gitignored).
