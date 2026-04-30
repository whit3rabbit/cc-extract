"""PE section discovery and data-start computation."""

from dataclasses import dataclass
import struct

from .constants import PE_DOS_MAGIC, PE_NT_SIGNATURE


@dataclass
class PeSection:
    pointer_to_raw_data: int
    size_of_raw_data: int


def is_pe(data):
    return len(data) >= 2 and struct.unpack_from("<H", data, 0)[0] == PE_DOS_MAGIC


def find_bun_pe_section(data):
    if len(data) < 0x40:
        return None
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset <= 0 or pe_offset + 24 > len(data):
        return None
    if struct.unpack_from("<I", data, pe_offset)[0] != PE_NT_SIGNATURE:
        return None

    num_sections = struct.unpack_from("<H", data, pe_offset + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe_offset + 20)[0]
    sections_start = pe_offset + 24 + optional_size

    for index in range(num_sections):
        base = sections_start + index * 40
        if base + 40 > len(data):
            return None
        name = data[base : base + 8]
        if name[:5] == b".bun\x00":
            return PeSection(
                size_of_raw_data=struct.unpack_from("<I", data, base + 16)[0],
                pointer_to_raw_data=struct.unpack_from("<I", data, base + 20)[0],
            )
    return None


def pe_data_start(section_offset):
    return section_offset
