# Bun Standalone Claude Code Binary Toolkit

> [!IMPORTANT]
> This project is not affiliated with Anthropic or Claude Code. It is intended for research and educational work on Claude Code packaged binaries.

`cc-extractor` is a standalone Python tool for downloading, inspecting, extracting, patching, and repacking Bun standalone bundles inside Claude Code binaries. The parser understands Mach-O, ELF, and PE layouts, and binary patching uses the shared parser and platform repack code instead of one-off format logic.

## Features

- Download Claude Code binary artifacts or the Anthropic NPM tarball.
- Inspect Bun bundle metadata without extracting files.
- Extract or unpack module contents and `.bundle_manifest.json`.
- Replace same-size modules or resize the entry JS module.
- Repack ELF, Mach-O, and PE fixture-compatible Bun payloads.
- Apply theme and prompt overlays directly to bundled `cli.js`.
- Use an unpacked Node fallback path for cases where running patched JS outside the native binary is preferable.
- Keep legacy extracted-text patch manifests through `patcher.py`.

Based in part on work by https://github.com/vicnaum/bun-demincer. Theme and prompt anchor logic is attributed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Install

```bash
pip install -e .
pip install -e '.[dev]'
```

## Usage

All commands can be run through `python3 main.py ...` or the installed `cc-extractor` console script.

### Download

```bash
python3 main.py download
python3 main.py download --latest
python3 main.py download 1.2.3
python3 main.py download --npm 1.2.3
```

### Inspect

```bash
python3 main.py inspect /path/to/claude
python3 main.py inspect /path/to/claude --json
```

### Extract Or Unpack

```bash
python3 main.py extract /path/to/claude ./extracted_files
python3 main.py unpack /path/to/claude --out ./extracted_files
python3 main.py extract /path/to/claude ./extracted_files --include-sourcemaps
```

Extraction writes module files plus `.bundle_manifest.json`. The manifest records platform, module struct size, entry point, byte count, section metadata, and per-module offsets needed by repack.

### Replace Entry JS

```bash
python3 main.py replace-entry /path/to/claude ./entry.js --out ./claude-patched
```

This resizes only the Bun entry module and repacks the binary through `binary_patcher.repack_binary`.

### Apply Binary Theme And Prompt Patches

```bash
python3 main.py apply-binary /path/to/claude --config ./config.json
python3 main.py apply-binary /path/to/claude --config ./config.json --overlays ./overlays.json
```

`config.json` may provide themes as either `{"themes": [...]}` or `{"settings": {"themes": [...]}}`. Prompt overlay misses are reported in the structured JSON result and are not fatal. Theme anchor misses return `anchor-not-found`.

### Legacy Text Patch Manifests

```bash
python3 main.py patch init ./my_patch
python3 main.py patch apply ./my_patch ./extracted_files
```

This remains separate from the binary patcher. It modifies extracted files according to patch manifests.

### Pack

```bash
python3 main.py pack ./modified_files /path/to/original_claude ./new_claude
```

`pack` is a compatibility wrapper. It rebuilds raw Bun bytes from `.bundle_manifest.json`, parses the base binary, and delegates container rewriting to `binary_patcher.repack_binary`.

## Python API

```python
from cc_extractor import parse_bun_binary, extract_all, replace_module, replace_entry_js, apply_patches
```

The core model is `BunBinaryInfo` and `BunModule` from `cc_extractor.bun_extract.types`.

## Architecture

```text
cc_extractor/
  __main__.py                 CLI entry point
  downloader.py               GCS and NPM download helpers
  download_picker.py          Interactive version picker

  bun_extract/
    constants.py              Shared constants and magic values
    types.py                  BunBinaryInfo, BunModule, exceptions
    parser.py                 Mach-O, ELF, and PE Bun parser
    macho.py                  Read-only Mach-O section scan
    elf.py                    ELF detection and data-start logic
    pe.py                     PE .bun section scan
    extract.py                Module writer and manifest generation
    replace.py                Same-size module replacement

  binary_patcher/
    replace_entry.py          Resize-capable entry JS replacement
    repack.py                 Platform repack dispatcher
    elf_resize.py             ELF header, section, and PT_LOAD resize
    macho_resize.py           Mach-O section resize and signature stripping
    pe_resize.py              PE .bun section resize with last-section guard
    theme.py                  Theme anchor patching
    prompts.py                Prompt overlay patching
    index.py                  Structured apply_patches orchestrator
    codesign.py               Soft macOS ad-hoc signing helper
    strip_bun_wrapper.py      Bun CJS wrapper stripping
    js_patch.py               Patch extracted entry JS
    unpack_and_patch.py       Extract, patch, package, and npm install fallback

  patcher.py                  Legacy extracted-text patch manifests
  bundler.py                  Compatibility pack wrapper over binary_patcher
  macho.py                    Legacy Mach-O mutation helper
```

## Development

```bash
pytest -q
python -m compileall -q cc_extractor tests
```

Network integration tests, if added later, should stay gated behind an explicit environment variable because real Claude Code binaries are large.
