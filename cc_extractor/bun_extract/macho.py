from dataclasses import dataclass
import struct

from .constants import (
    MACHO_HEADER_SCAN_BYTES,
    MACHO_MAGIC_64,
    MACHO_MAGIC_64_BE,
    MACHO_MAGIC_FAT,
    MACHO_MAGIC_FAT_LE,
    MACHO_SECTION_HEADER_SIZE,
)

LC_CODE_SIGNATURE = 0x1D


@dataclass
class MachoSection:
    section_offset: int
    section_size: int
    has_code_signature: bool = False


def is_macho(data):
    if len(data) < 4:
        return False
    magic = struct.unpack_from("<I", data, 0)[0]
    return magic in {
        MACHO_MAGIC_64,
        MACHO_MAGIC_64_BE,
        MACHO_MAGIC_FAT,
        MACHO_MAGIC_FAT_LE,
    }


def find_bun_section(data):
    limit = min(len(data), MACHO_HEADER_SCAN_BYTES)
    for offset in range(0, max(0, limit - 56)):
        if (
            data[offset : offset + 6] == b"__bun\x00"
            and data[offset + 16 : offset + 21] == b"__BUN"
        ):
            section_size = struct.unpack_from("<Q", data, offset + 40)[0]
            section_offset = struct.unpack_from("<I", data, offset + 48)[0]
            return MachoSection(
                section_offset=section_offset,
                section_size=section_size,
                has_code_signature=_scan_for_code_signature_cmd(data, limit),
            )
    return None


def macho_data_start(section_offset):
    return section_offset + MACHO_SECTION_HEADER_SIZE


def _scan_for_code_signature_cmd(data, limit):
    for offset in range(0, max(0, limit - 8), 4):
        if struct.unpack_from("<I", data, offset)[0] != LC_CODE_SIGNATURE:
            continue
        cmdsize = struct.unpack_from("<I", data, offset + 4)[0]
        if cmdsize == 16:
            return True
    return False
