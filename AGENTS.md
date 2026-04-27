# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

A standalone Python toolkit for extracting, patching, and repacking Bun standalone bundles inside Claude Code binaries. Used for research and educational purposes.

## Commands

```bash
# Install
pip install -e .
pip install -e '.[dev]'

# Run commands
python3 main.py download [version]
python3 main.py download --latest
python3 main.py download --npm [version]
python3 main.py inspect <binary> --json
python3 main.py extract <binary> <dir>
python3 main.py unpack <binary> --out <dir>
python3 main.py replace-entry <binary> <entry-js> --out <binary>
python3 main.py apply-binary <binary> --config <config.json> [--overlays <overlays.json>]
python3 main.py pack <dir> <base> <out>
pytest -q
```

## Architecture

```text
main.py / __main__.py        -> CLI entry point with argparse subcommands
downloader.py                -> Fetches binaries from Google Cloud Storage or NPM tarballs
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
extractor.py                 -> Compatibility wrapper over bun_extract
bundler.py                   -> Compatibility wrapper over binary_patcher.repack_binary
patcher.py                   -> Legacy extracted-text patch manifests
macho.py                     -> Legacy Mach-O header update helper
```

## Behavior Notes

- `parse_bun_binary` is the single source of truth for binary layout.
- `extractor.py` and `bundler.py` are compatibility layers, not independent parsers.
- `patcher.py` is only for old extracted-text patch manifests. Keep it separate from `binary_patcher`.
- Prompt anchor misses are recorded and non-fatal.
- Theme anchor misses are fatal structured failures.
- Mach-O signing is explicit and soft-failing through `codesign.py`.
- Unpacked fallback helpers support Python `.bundle_manifest.json` and TS-style `manifest.json`.

## Development Notes

- Tests use `pytest`.
- Runtime dependencies: `ratatui`, `tqdm`.
- Python 3.8+.
- No extra runtime dependency is required for P5. The unpacked fallback shells out to `npm` only when that helper is used.
