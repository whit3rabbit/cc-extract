# Bun Standalone Claude Code Binary Toolkit

> [!IMPORTANT]
> This project is not affiliated with Anthropic or Claude Code. It is intended for research and educational work on Claude Code packaged binaries.

`cc-extractor` is a standalone Python tool for downloading, inspecting, extracting, patching, and repacking Bun standalone bundles inside Claude Code binaries. It includes an interactive TUI for common workflows and a variant management system for creating isolated, patched Claude Code installations.

## Features

- Interactive TUI with dashboard wizard, patch profile management, and variant creation.
- Download Claude Code binary artifacts or the Anthropic NPM tarball.
- Inspect Bun bundle metadata without extracting files.
- Extract or unpack module contents and `.bundle_manifest.json`.
- Replace same-size modules or resize the entry JS module.
- Repack ELF, Mach-O, and PE Bun payloads.
- Apply theme and prompt overlays directly to bundled `cli.js`.
- Create isolated Claude Code variants with provider presets and model overrides.
- Manage patch profiles for reusable build configurations.
- Prompt extraction with tree-sitter-based tooling.

Based in part on work by https://github.com/vicnaum/bun-demincer. Theme and prompt anchor logic is attributed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Install

```bash
pip install -e .
pip install -e '.[dev]'
```

## Usage

Running `cc-extractor` without arguments in a TTY opens the interactive TUI. All commands are also available through `python3 main.py ...` or the installed `cc-extractor` console script.

### Quick Start

```bash
cc-extractor                        # open the TUI
cc-extractor --help                 # show CLI help
```

### TUI

The TUI opens to the Dashboard tab by default. Navigate with arrow keys, `Tab`/`Shift-Tab` to switch tabs, `Enter` to activate, `Esc` or `Backspace` to go back.

**Tabs:**

| Tab | Description |
|-----|-------------|
| Dashboard | 4-step wizard: pick source, select patches, load or save profiles, review and build. |
| Inspect | View Bun bundle metadata for a selected binary. |
| Extract | Extract or unpack a binary to disk. |
| Patch | Apply patch packages to a source binary. |
| Variants | 6-step wizard: pick provider, name the variant, configure credentials, set model overrides, select tweaks, review and create. |

**Keyboard controls:**

| Key | Action |
|-----|--------|
| Arrows | Navigate lists |
| Tab / Right | Switch tab |
| Esc / Backspace | Go back |
| Enter | Activate selection |
| Space | Toggle selection |
| q | Quit |
| t | Cycle theme |
| b | Go back |
| r | Refresh (Dashboard) |

**Themes:** hacker-bbs (default), unicorn, dark, light.

### Download

```bash
cc-extractor download
cc-extractor download --latest
cc-extractor download 1.2.3
cc-extractor download --npm 1.2.3
```

### Inspect

```bash
cc-extractor inspect /path/to/claude
cc-extractor inspect /path/to/claude --json
```

### Extract / Unpack

```bash
cc-extractor extract /path/to/claude ./extracted_files
cc-extractor unpack /path/to/claude --out ./extracted_files
cc-extractor extract /path/to/claude ./extracted_files --include-sourcemaps
```

Extraction writes module files plus `.bundle_manifest.json`. The manifest records platform, module struct size, entry point, byte count, section metadata, and per-module offsets needed by repack.

### Replace Entry JS

```bash
cc-extractor replace-entry /path/to/claude ./entry.js --out ./claude-patched
```

Resizes only the Bun entry module and repacks the binary through `binary_patcher.repack_binary`.

### Apply Binary Theme And Prompt Patches

```bash
cc-extractor apply-binary /path/to/claude --config ./config.json
cc-extractor apply-binary /path/to/claude --config ./config.json --overlays ./overlays.json
```

`config.json` may provide themes as either `{"themes": [...]}` or `{"settings": {"themes": [...]}}`. Prompt overlay misses are reported in the structured JSON result and are not fatal. Theme anchor misses return `anchor-not-found`. On Mach-O binaries, patches that would grow the bundled entry JS are skipped without writing and return `ok: true` with `skipped_reason: "macho-grow-not-supported"`.

### Patch Manifests

```bash
cc-extractor patch init ./my_patch
cc-extractor patch apply ./my_patch ./extracted_files
cc-extractor patch apply ./my_patch ./extracted_files --check
cc-extractor patch apply ./my_patch ./extracted_files --binary /path/to/claude --source-version 1.2.3
```

Creates or applies text patch manifests against extracted bundle files. `--check` validates without writing. `--binary` and `--source-version` override source metadata for cross-version patches.

### Variants

Variants are isolated, patched Claude Code installations addressed by name or id. Each variant pins a provider, optional model overrides, and a set of tweaks.

```bash
cc-extractor variant providers                           # list provider presets
cc-extractor variant create --name my-cc --provider kimi # create a variant
cc-extractor variant list                                # list all variants
cc-extractor variant show my-cc                          # show variant metadata
cc-extractor variant apply my-cc                         # re-apply saved settings
cc-extractor variant update my-cc                        # update to latest version
cc-extractor variant update --all                        # update all variants
cc-extractor variant doctor my-cc                        # health check
cc-extractor variant doctor --all                        # check all variants
cc-extractor variant run my-cc -- [args...]              # run variant wrapper
cc-extractor variant remove my-cc --yes                  # remove a variant
```

**Create options:**

| Flag | Description |
|------|-------------|
| `--name` | Variant name, also used as wrapper command. |
| `--provider` | Provider preset key (required). |
| `--claude-version` | Target version, `latest`, or `stable`. |
| `--patch-profile` | Apply a saved patch profile. |
| `--tweak` | Curated tweak id (repeatable). |
| `--credential-env` | Environment variable for provider credentials. |
| `--api-key` | API key stored locally (requires `--store-secret`). |
| `--extra-env` | Additional `KEY=VALUE` env entries (repeatable). |
| `--force` | Overwrite an existing variant. |
| Model overrides | `--opus`, `--sonnet`, `--haiku`, `--default`, `--small-fast`, `--subagent`. |

### Pack

```bash
cc-extractor pack ./modified_files /path/to/original_claude ./new_claude
```

Rebuilds raw Bun bytes from `.bundle_manifest.json`, parses the base binary, and delegates container rewriting to `binary_patcher.repack_binary`.

## Python API

```python
from cc_extractor import (
    download_binary,
    download_npm,
    extract_all,
    pack_bundle,
    apply_patches,
    parse_bun_binary,
    replace_entry_js,
    replace_module,
)
```

The core model is `BunBinaryInfo` and `BunModule` from `cc_extractor.bun_extract.types`.

## Architecture

```text
cc_extractor/
  __init__.py                   Public API with lazy imports
  __main__.py                   CLI entry point and variant dispatcher
  _utils.py                     Cross-module stdlib helpers
  cli/
    parsers.py                  Argparse parser tree
    handlers.py                 Per-subcommand handlers
    payloads.py                 JSON payload helpers
  tui/
    __init__.py                 TUI action layer and main loop
    state.py                    TuiState dataclass and refresh
    themes.py                   Theme definitions
    options.py                  Menu option builders
    rendering.py                Frame rendering
    dashboard.py                Dashboard state management
    variant_actions.py          Variant wizard actions
    keys.py                     Key binding dispatch
    nav.py                      Navigation handlers
    _const.py                   Constants and data classes
    _runtime.py                 ratatui app setup
  workspace/
    __init__.py                 Re-exports
    paths.py                    Workspace path helpers
    models.py                   NativeArtifact, PatchPackage, PatchProfile
    artifacts.py                Artifact scanning
    patches.py                  Patch package helpers
    settings.py                 TUI settings persistence
  variants/
    __init__.py                 Variant lifecycle actions
    model.py                    Variant data model
    builder.py                  Variant builder
    tweaks.py                   Curated tweak definitions
    wrapper.py                  Wrapper script generation
  bun_extract/
    constants.py                Shared constants and magic values
    types.py                    BunBinaryInfo, BunModule, exceptions
    parser.py                   Mach-O, ELF, and PE Bun parser
    macho.py                    Read-only Mach-O section scan
    elf.py                      ELF detection and data-start logic
    pe.py                       PE .bun section scan
    extract.py                  Module writer and manifest generation
    replace.py                  Same-size module replacement
  binary_patcher/
    replace_entry.py            Resize-capable entry JS replacement
    repack.py                   Platform repack dispatcher
    elf_resize.py               ELF header, section, and PT_LOAD resize
    macho_resize.py             Mach-O section resize and signature stripping
    pe_resize.py                PE .bun section resize with last-section guard
    theme.py                    Theme anchor patching
    prompts.py                  Prompt overlay patching
    index.py                    Structured apply_patches orchestrator
    codesign.py                 Soft macOS ad-hoc signing helper
    js_patch.py                 Patch extracted entry JS
    unpack_and_patch.py         Extract, patch, package, and npm install fallback
  providers.py                  Provider templates and env builders
  patcher.py                    Legacy extracted-text patch manifests
  patch_workflow.py             High-level patch, repack, and metadata workflow
  downloader.py                 GCS and NPM download helpers
  download_index.py             Cached live/seed download version index
  download_picker.py            Interactive version picker
  extractor.py                  Compatibility wrapper over bun_extract
  bundler.py                    Compatibility wrapper over binary_patcher
  variant_tweaks.py             Backwards-compat shim
  tools/
    prompt_extractor.py         Tree-sitter prompt extractor
    extract_prompt_versions.py  Batch prompt extraction and validation
```

## Development

```bash
python3 -m pytest -q
python3 -m compileall -q cc_extractor tests
ruff check cc_extractor/ tools/ main.py
```

The default test suite does not download real Claude Code binaries. Run the gated integration test explicitly when you need live binary coverage:

```bash
CC_EXTRACTOR_RUN_REAL_BINARY_TEST=1 python3 -m pytest -q tests/test_integration_real_binary.py
CC_EXTRACTOR_RUN_REAL_BINARY_TEST=1 CC_EXTRACTOR_REAL_BINARY_VERSION=2.1.119 python3 -m pytest -q tests/test_integration_real_binary.py
```

The integration test downloads the host-platform Claude Code binary, patches a temporary copy with a tiny theme config, executes `claude --version`, verifies patched JS markers, and extracts the patched bundle. It is intentionally gated because the download is large and depends on network access.
