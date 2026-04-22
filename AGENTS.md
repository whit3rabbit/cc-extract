# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

A standalone Python tool for extracting and repacking Bun bundles inside Claude Code Mach-O binaries. Used for research and educational purposes.

## Commands

```bash
# Install
pip install -e .
pip install -e '.[dev]'  # Include pytest

# Run commands
python3 main.py download [version]       # Download Claude Code artifact, or pick interactively when omitted
python3 main.py download --latest        # Download the latest Claude Code artifact without prompting
python3 main.py download --npm [version] # Download Anthropic NPM tarball instead
python3 main.py extract <binary> <dir>   # Extract Bun bundle from a Claude Code binary
python3 main.py pack <dir> <base> <out>  # Repack directory into a Claude Code binary
pytest -q                                # Run tests
```

## Architecture

```
main.py / __main__.py     → CLI entry point with argparse subcommands
downloader.py             → Fetches binaries from Google Cloud Storage or NPM tarballs
extractor.py              → Mach-O parsing to locate and extract __BUN section entries
bundler.py                → Reconstructs Bun bundle format and manages binary injection
macho.py                  → Handles low-level Mach-O header updates (filesize, vmsize, offsets)
```

- **download**: Downloads Claude Code binary artifacts or the Anthropic NPM package
- **extract**: Parses Mach-O to find `__BUN` segment, extracts files + generates `.bundle_manifest.json`
- **pack**: Uses manifest to rebuild bundle, appends to binary if larger than original, updates Mach-O headers

## Development Notes

- Tests are implemented with `pytest`
- Dependencies: `ratatui`, `tqdm`
- Python 3.8+
