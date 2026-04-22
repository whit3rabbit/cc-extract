# Bun Bundle Extractor/Packer

> [!IMPORTANT]
> This project is not affiliated with Claude Code. It is intended for research and educational work on Claude Code packaged binaries.

A standalone Python tool for downloading, extracting, and repacking Bun bundles in Claude Code Mach-O binaries.

- Download
- Extract
- Patch
- Repack

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

### 2. Extract (Unbundle)
Extracts the internal Claude Code Bun filesystem into a directory.
```bash
python3 main.py extract downloads/2.1.117/claude ./extracted_files
```
To record a source version for later patch targeting:
```bash
python3 main.py extract /path/to/claude ./extracted_files --source-version 1.2.3
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

### 4. Pack (Bundle)
Repacks a directory back into a Claude Code binary.
```bash
python3 main.py pack ./modified_files /path/to/original_claude ./new_claude
```
If the new bundle is larger than the original, it will be automatically appended and Mach-O headers updated.

## Development

Run the test suite:
```bash
pytest -q
```

## Internal Modules
- `downloader.py`: Fetches binaries from GCS or NPM tarballs.
- `extractor.py`: Mach-O parsing to locate and extract `__BUN` sections.
- `bundler.py`: Reconstructs Bun bundle format and manages binary injection.
- `macho.py`: Handles low-level Mach-O header updates.
