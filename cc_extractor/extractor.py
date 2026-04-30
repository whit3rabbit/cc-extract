import struct
from pathlib import Path

from .bun_extract import parse_bun_binary
from .bun_extract.extract import extract_all as extract_all_from_info
from .bun_extract.macho import find_bun_section as find_macho_bun_section
from .bun_extract.macho import is_macho
from .patcher import write_source_metadata
from .workspace import (
    extraction_metadata_path,
    extraction_paths,
    file_sha256,
    native_artifact_from_path,
    read_json,
    write_extraction_metadata,
    write_json,
)

TRAILER = b"\n---- Bun! ----\n"
SECTION_HEADER_SIZE = 8


def read_u32(data, offset, endian="<"):
    return struct.unpack_from(endian + "I", data, offset)[0]


def read_u64(data, offset, endian="<"):
    return struct.unpack_from(endian + "Q", data, offset)[0]


def find_bun_section_offset(binary_path):
    data = Path(binary_path).read_bytes()
    if not is_macho(data):
        raise ValueError("Unsupported binary format (expected Mach-O 64-bit).")

    section = find_macho_bun_section(data)
    if section is None:
        raise ValueError("Failed to locate __BUN,__bun section.")

    return data, section.section_offset, section.section_size, "<"


def find_bun_section(binary_path):
    data, fileoff, size, endian = find_bun_section_offset(binary_path)
    return data[fileoff : fileoff + size], fileoff, size, endian


def extract_all(
    binary_path,
    out_dir=None,
    source_version=None,
    write_sourcemaps=False,
    manifest=True,
):
    binary_path = Path(binary_path)
    data = binary_path.read_bytes()
    info = parse_bun_binary(data)
    artifact = native_artifact_from_path(binary_path)

    if out_dir is None:
        source_sha256 = artifact.sha256 if artifact else file_sha256(binary_path)
        effective_version = source_version or (artifact.version if artifact else "unknown")
        platform_key = artifact.platform if artifact else info.platform
        _, out_dir = extraction_paths(effective_version, platform_key, source_sha256)
        manifest_path = out_dir / ".bundle_manifest.json"
        metadata_path = extraction_metadata_path(out_dir)
        if manifest and manifest_path.exists() and metadata_path.exists():
            metadata = read_json(metadata_path)
            if (
                metadata.get("sourceSha256") == source_sha256
                and metadata.get("writeSourcemaps") == write_sourcemaps
            ):
                print(f"[*] Reusing extraction at {out_dir}")
                return read_json(manifest_path)
    else:
        effective_version = source_version
        platform_key = None
        source_sha256 = None

    result = extract_all_from_info(
        data,
        info,
        out_dir,
        write_sourcemaps=write_sourcemaps,
        manifest=manifest,
    )

    write_source_metadata(out_dir, binary_path, source_version=source_version)
    if source_sha256 is not None and platform_key is not None:
        metadata_path = write_extraction_metadata(
            out_dir,
            binary_path,
            effective_version,
            platform_key,
            source_sha256,
        )
        metadata = read_json(metadata_path)
        metadata["writeSourcemaps"] = write_sourcemaps
        metadata["manifest"] = manifest

        write_json(metadata_path, metadata)

    manifest_data = result.manifest or {}
    print(f"[+] Extracted {len(info.modules)} modules to {out_dir}")
    return manifest_data


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: extractor.py <binary> <out_dir>")
    else:
        extract_all(sys.argv[1], sys.argv[2])
