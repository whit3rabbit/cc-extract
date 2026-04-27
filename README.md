# Bun Standalone Binary Extractor

> [!IMPORTANT]
> This project is not affiliated with Claude Code. It is intended for research and educational work on Claude Code packaged binaries.

A standalone Python tool for downloading and extracting Bun standalone bundles in Claude Code binaries. The parser understands Mach-O, ELF, and PE Bun payload layouts.

- Download
- Inspect
- Extract or unpack
- Patch
- Repack

Based on work by: https://github.com/vicnaum/bun-demincer

## Getting Started

### 1. Clone the repository
```bash
git clone https://github.com/whit3rabbit/cc-extract.git
cd cc-extract
```

### 2. Install dependencies
```bash
pip install -e .
```
*(Optional) Install development/test dependencies:* `pip install -e '.[dev]'`

## Usage

All commands can be run via `python3 main.py [command]`.

### 1. Download Claude Code Artifacts

Running the download command without arguments opens an **interactive version picker**:
```bash
python3 main.py download
```

**Other Options:**
- **Specific Version**: `python3 main.py download 1.2.3`
- **Latest Release**: `python3 main.py download --latest` (skips picker)
- **NPM Tarball**: `python3 main.py download --npm [version]`

### 2. Inspect
Print parsed Bun metadata without extracting files.
```bash
python3 main.py inspect downloads/2.1.117/claude
python3 main.py inspect downloads/2.1.117/claude --json
```

### 3. Extract (Unbundle)
Extracts the internal Claude Code Bun filesystem into a directory.
```bash
python3 main.py extract downloads/2.1.117/claude ./extracted_files
```
The TypeScript-compatible alias is also available:
```bash
python3 main.py unpack downloads/2.1.117/claude --out ./extracted_files
```
To record a source version for later patch targeting:
```bash
python3 main.py extract /path/to/claude ./extracted_files --source-version 1.2.3
```
To include sourcemaps:
```bash
python3 main.py extract /path/to/claude ./extracted_files --include-sourcemaps
```

### 4. Patch
Create a patch scaffold:
```bash
python3 main.py patch init ./my_patch
```

Apply a patch to an extracted bundle:
```bash
python3 main.py patch apply ./my_patch ./extracted_files
```

### 5. Pack (Bundle)
Repacks a directory back into a Claude Code binary.
```bash
python3 main.py pack ./modified_files /path/to/original_claude ./new_claude
```
This command is still the legacy compatibility path. The shared cross-platform resize and repack engine is planned after the parser and extraction migration.

## Development

Run the test suite:
```bash
pytest -q
```

## Internal Modules
- `downloader.py`: Fetches binaries from GCS or NPM tarballs.
- `bun_extract/`: Shared Mach-O, ELF, and PE Bun parser and extraction writer.
- `extractor.py`: Compatibility wrapper over `bun_extract`.
- `bundler.py`: Legacy compatibility packer. Core cross-platform repack is planned for `binary_patcher/`.
- `macho.py`: Legacy Mach-O header update helper.
