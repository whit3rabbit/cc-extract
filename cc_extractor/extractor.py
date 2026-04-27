import struct
from pathlib import Path

from .bun_extract import parse_bun_binary
from .bun_extract.extract import extract_all as extract_all_from_info
from .bun_extract.macho import find_bun_section as find_macho_bun_section
from .bun_extract.macho import is_macho
from .patcher import write_source_metadata

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
    out_dir,
    source_version=None,
    write_sourcemaps=False,
    manifest=True,
):
    data = Path(binary_path).read_bytes()
    info = parse_bun_binary(data)
    result = extract_all_from_info(
        data,
        info,
        out_dir,
        write_sourcemaps=write_sourcemaps,
        manifest=manifest,
    )

    write_source_metadata(out_dir, binary_path, source_version=source_version)

    manifest_data = result.manifest or {}
    print(f"[+] Extracted {len(info.modules)} modules to {out_dir}")
    return manifest_data


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: extractor.py <binary> <out_dir>")
    else:
        extract_all(sys.argv[1], sys.argv[2])
