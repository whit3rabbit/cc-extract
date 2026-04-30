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

# Prompt extraction
.venv/bin/python tools/prompt_extractor.py <entry-js> --output prompts/<version>.json --version-hint <version>
.venv/bin/python tools/extract_prompt_versions.py --local
.venv/bin/python tools/extract_prompt_versions.py --versions 2.1.123 2.1.122 --force-prompts
.venv/bin/python tools/extract_prompt_versions.py --all --force-prompts
```

## Architecture

```text
main.py / __main__.py        -> CLI entry point with argparse subcommands
tui.py                       -> ratatui dashboard wizard and advanced tabs
workspace.py                 -> Centralized downloads, extractions, patch packages, profiles, and metadata
downloader.py                -> Fetches binaries from Google Cloud Storage or NPM tarballs
download_index.py            -> Cached live/seed download version index
download_picker.py           -> Interactive version picker
bun_extract/parser.py        -> Shared Bun binary parser for Mach-O, ELF, and PE
bun_extract/extract.py       -> Writes extracted module files and `.bundle_manifest.json`
bun_extract/replace.py       -> Same-size in-place module replacement
binary_patcher/replace_entry.py -> Resize-capable entry JS replacement
binary_patcher/repack.py     -> Repack dispatcher for ELF, Mach-O, and PE
binary_patcher/*_resize.py   -> Platform-specific resize logic
binary_patcher/theme.py      -> Theme anchor patching
binary_patcher/prompts.py    -> Prompt overlay patching
binary_patcher/index.py      -> Structured apply_patches API
binary_patcher/codesign.py   -> Soft macOS ad-hoc signing helper
binary_patcher/js_patch.py   -> Patch extracted entry JS
binary_patcher/unpack_and_patch.py -> Unpacked Node fallback path
patch_workflow.py            -> Extract, apply patch packages, repack, and write patched metadata
extractor.py                 -> Compatibility wrapper over bun_extract
bundler.py                   -> Compatibility wrapper over binary_patcher.repack_binary
patcher.py                   -> Legacy extracted-text patch manifests
macho.py                     -> Legacy Mach-O header update helper
tools/prompt_extractor.py    -> Tree-sitter prompt extractor that writes tweakcc-style JSON
tools/extract_prompt_versions.py -> Download, extract, write, and validate prompt JSON files
prompts/*.json               -> Generated prompt catalogs keyed by Claude Code version
```

## Behavior Notes

- `parse_bun_binary` is the single source of truth for binary layout.
- `extractor.py` and `bundler.py` are compatibility layers, not independent parsers.
- `patcher.py` is only for old extracted-text patch manifests. Keep it separate from `binary_patcher`.
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

## Development Notes

- Use `.venv/bin/python` for Python commands from the repository root.
- Tests use `pytest`.
- Prompt extractor tests live under `tests/`.
- Prompt extraction dev dependencies include `tree-sitter` and `tree-sitter-javascript`.
- Runtime dependencies: `ratatui`, `tqdm`.
- Python 3.8+.
- No extra runtime dependency is required for P5. The unpacked fallback shells out to `npm` only when that helper is used.
- For TUI changes, add widget-independent state tests and smoke test with the TUI MCP using a temporary `CC_EXTRACTOR_WORKSPACE`.
- In TUI MCP smoke tests, prefer `Tab`, `Enter`, `Space`, text input, and `q`; verify arrow-key names before relying on them.
- Do not stage or commit submodule changes, including `vendor/tweakcc`, unless explicitly requested.
