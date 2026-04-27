# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

A standalone Python tool for extracting and eventually repacking Bun standalone bundles inside Claude Code binaries. Used for research and educational purposes.

## Commands

```bash
# Install
pip install -e .
pip install -e '.[dev]'  # Include pytest

# Run commands
python3 main.py download [version]       # Download Claude Code artifact, or pick interactively when omitted
python3 main.py download --latest        # Download the latest Claude Code artifact without prompting
python3 main.py download --npm [version] # Download Anthropic NPM tarball instead
python3 main.py inspect <binary> --json  # Inspect Bun platform, module table, and entry point
python3 main.py extract <binary> <dir>   # Extract Bun bundle from a Claude Code binary
python3 main.py unpack <binary> --out <dir> # Alias for extract
python3 main.py pack <dir> <base> <out>  # Repack directory into a Claude Code binary
pytest -q                                # Run tests
```

## Architecture

```
main.py / __main__.py     → CLI entry point with argparse subcommands
downloader.py             → Fetches binaries from Google Cloud Storage or NPM tarballs
bun_extract/parser.py     → Shared Bun binary parser for Mach-O, ELF, and PE
bun_extract/extract.py    → Writes extracted module files and `.bundle_manifest.json`
extractor.py              → Compatibility wrapper over bun_extract
bundler.py                → Legacy compatibility packer until binary_patcher repack lands
macho.py                  → Legacy Mach-O header update helper
```

- **download**: Downloads Claude Code binary artifacts or the Anthropic NPM package
- **inspect**: Parses a binary and reports platform, module count, module size, and entry path
- **extract/unpack**: Parses Mach-O, ELF, or PE Bun payloads, extracts files, and generates `.bundle_manifest.json`
- **pack**: Legacy manifest pack path, cross-platform resize is planned in `binary_patcher`

## Development Notes

- Tests are implemented with `pytest`
- Dependencies: `ratatui`, `tqdm`
- Python 3.8+
