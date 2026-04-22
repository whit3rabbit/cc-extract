# Bun Bundle Extractor/Packer

> [!IMPORTANT]
> This project is not affiliated with Claude Code. It is intended for research and educational work on Claude Code packaged binaries.

A standalone Python tool for downloading, extracting, and repacking Bun bundles in Claude Code Mach-O binaries.

- Download
- Extract
- Patch
- Repack

## Run

Install from the repo root:
```bash
pip install -e .
```

Install with test dependencies:
```bash
pip install -e '.[dev]'
```

Run commands either through the source entrypoint:
```bash
python3 main.py --help
```

Or through the installed console script:
```bash
cc-extractor --help
```

## Usage

### 1. Download Claude Code Artifacts
Downloads a specific Claude Code release artifact for your platform, or opens an interactive version picker when no version is provided.
```bash
python3 main.py download [version]
```
Always download the latest release without prompting:
```bash
python3 main.py download --latest
```
Download the Anthropic NPM tarball instead:
```bash
python3 main.py download --npm [version]
```
Use `--latest` there too if you want the newest tarball immediately.

Example:
```bash
python3 main.py download 1.2.3
```

### 2. Extract (Unbundle)
Extracts the internal Claude Code Bun filesystem into a directory.
```bash
python3 main.py extract downloads/2.1.117/claude ./extracted_files
```
To record a source version for later patch targeting:
```bash
python3 main.py extract /path/to/claude ./extracted_files --source-version 1.2.3
```
This generates:
- `.bundle_manifest.json` with the metadata needed to reconstruct the bundle faithfully.
- `.bundle_source.json` with the source binary SHA-256 and optional `source_version`.

Example:
```bash
python3 main.py extract ./downloads/1.2.3/claude ./workdir/claude-1.2.3 --source-version 1.2.3
```

### 3. Patch
Create a patch scaffold:
```bash
python3 main.py patch init ./my_patch
```
Apply a patch to an extracted bundle:
```bash
python3 main.py patch apply ./my_patch ./extracted_files
```
Validate a patch without writing any files:
```bash
python3 main.py patch apply ./my_patch ./extracted_files --check
```
If the patch targets a specific version or checksum and the extracted directory does not already have matching metadata, pass overrides:
```bash
python3 main.py patch apply ./my_patch ./extracted_files --source-version 1.2.3 --binary /path/to/claude
```

Patch folders contain:
- `patch.json`
- `blocks/` for multiline find/replace text assets

Supported patch operations in v1:
- `replace_string`: exact literal string replacement
- `replace_block`: exact literal multiline block replacement using external text files

Example workflow:
```bash
python3 main.py patch init ./patches/enable-feature
python3 main.py patch apply ./patches/enable-feature ./workdir/claude-1.2.3 --check
python3 main.py patch apply ./patches/enable-feature ./workdir/claude-1.2.3
```

### 4. Pack (Bundle)
Repacks a directory back into a Claude Code binary.
```bash
python3 main.py pack ./modified_files /path/to/original_claude ./new_claude
```
If the new bundle is larger than the original, it will be automatically appended to the binary, and the Mach-O `LC_SEGMENT_64` and `LC_SECTION_64` headers for `__BUN` will be updated with the new offset and size.

Example:
```bash
python3 main.py pack ./workdir/claude-1.2.3 ./downloads/1.2.3/claude ./dist/claude-1.2.3-patched
```

## Development

Run the test suite:
```bash
pytest -q
```

Runtime notes:
- Downloads work from a bare source checkout with stdlib HTTP.
- `ratatui` enables the full-screen version picker.
- `tqdm` enables download progress bars.

## Internal Modules
- `downloader.py`: Fetches binaries from Google Cloud Storage or NPM tarballs.
- `extractor.py`: Mach-O parsing to locate and extract the `__BUN` section entries.
- `bundler.py`: Reconstructs the Bun bundle format and manages binary injection.
- `macho.py`: Handles low-level Mach-O header updates (filesize, vmsize, offsets).
