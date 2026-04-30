"""Mach-O binary resize and code-signature stripping for the .bun section."""

import struct
from dataclasses import dataclass

from cc_extractor.bun_extract.constants import (
    MACHO_HEADER_SCAN_BYTES,
    MACHO_MAGIC_64,
    MACHO_MAGIC_64_BE,
    MACHO_SECTION_HEADER_SIZE,
    OFFSETS_SIZE,
    TRAILER,
)

LC_CODE_SIGNATURE = 0x1D
LC_SEGMENT_64 = 0x19
MACH_HEADER_64_SIZE = 32
LINKEDIT_SEGNAME = "__LINKEDIT"


@dataclass
class MachoRepackResult:
    buf: bytes
    signature_stripped: bool = False

    @property
    def data(self):
        return self.buf


def repack_macho(data, info, new_raw_bytes, new_offsets_struct):
    new_raw_bytes = bytes(new_raw_bytes)
    new_offsets_struct = bytes(new_offsets_struct)
    if len(new_offsets_struct) != OFFSETS_SIZE:
        raise ValueError(
            f"Mach-O repack: offsets struct must be {OFFSETS_SIZE} bytes, got {len(new_offsets_struct)}"
        )
    if info.section_offset is None:
        raise ValueError("Mach-O repack: BunBinaryInfo missing section_offset")

    section_header_offset = _find_bun_section_header_offset(data)
    if section_header_offset is None:
        raise ValueError("Mach-O repack: could not relocate __BUN section_64 struct for header rewrite")

    pre_section = bytearray(data[: info.section_offset])
    signature_stripped = False
    code_sig = _find_code_signature_lc(pre_section)
    if code_sig is not None:
        linkedit = _find_linkedit_segment(pre_section)
        if linkedit is not None:
            sig_size = code_sig["datasize"]
            new_filesize = max(0, linkedit["filesize"] - sig_size)
            new_vmsize = max(0, linkedit["vmsize"] - sig_size)
            struct.pack_into("<Q", pre_section, linkedit["lc_offset"] + 48, new_filesize)
            struct.pack_into("<Q", pre_section, linkedit["lc_offset"] + 32, new_vmsize)
        _strip_code_signature(pre_section, code_sig)
        signature_stripped = True

    new_section_inner_size = len(new_raw_bytes) + OFFSETS_SIZE + len(TRAILER)
    new_section_payload_size = MACHO_SECTION_HEADER_SIZE + new_section_inner_size
    struct.pack_into("<Q", pre_section, section_header_offset + 40, new_section_payload_size)

    size_header = struct.pack("<Q", len(new_raw_bytes))
    return MachoRepackResult(
        buf=b"".join([bytes(pre_section), size_header, new_raw_bytes, new_offsets_struct, TRAILER]),
        signature_stripped=signature_stripped,
    )


def _is_macho_64(data):
    if len(data) < 4:
        return False
    magic = struct.unpack_from("<I", data, 0)[0]
    return magic in {MACHO_MAGIC_64, MACHO_MAGIC_64_BE}


def _find_bun_section_header_offset(data):
    limit = min(len(data), MACHO_HEADER_SCAN_BYTES)
    for offset in range(0, max(0, limit - 56)):
        if (
            data[offset : offset + 6] == b"__bun\x00"
            and data[offset + 16 : offset + 21] == b"__BUN"
        ):
            return offset
    return None


def _find_code_signature_lc(data):
    if not _is_macho_64(data) or len(data) < MACH_HEADER_64_SIZE:
        return None
    ncmds = struct.unpack_from("<I", data, 16)[0]
    sizeofcmds = struct.unpack_from("<I", data, 20)[0]
    if ncmds == 0 or sizeofcmds == 0:
        return None

    cursor = MACH_HEADER_64_SIZE
    end = MACH_HEADER_64_SIZE + sizeofcmds
    if end > len(data):
        return None
    for _ in range(ncmds):
        if cursor + 8 > end:
            return None
        cmd = struct.unpack_from("<I", data, cursor)[0]
        cmdsize = struct.unpack_from("<I", data, cursor + 4)[0]
        if cmdsize < 8 or cursor + cmdsize > end:
            return None
        if cmd == LC_CODE_SIGNATURE and cmdsize == 16:
            return {
                "lc_offset": cursor,
                "cmdsize": cmdsize,
                "dataoff": struct.unpack_from("<I", data, cursor + 8)[0],
                "datasize": struct.unpack_from("<I", data, cursor + 12)[0],
            }
        cursor += cmdsize
    return None


def _find_linkedit_segment(data):
    if len(data) < MACH_HEADER_64_SIZE:
        return None
    ncmds = struct.unpack_from("<I", data, 16)[0]
    sizeofcmds = struct.unpack_from("<I", data, 20)[0]
    cursor = MACH_HEADER_64_SIZE
    end = MACH_HEADER_64_SIZE + sizeofcmds
    if end > len(data):
        return None

    for _ in range(ncmds):
        if cursor + 8 > end:
            return None
        cmd = struct.unpack_from("<I", data, cursor)[0]
        cmdsize = struct.unpack_from("<I", data, cursor + 4)[0]
        if cmdsize < 8 or cursor + cmdsize > end:
            return None
        if cmd == LC_SEGMENT_64 and cmdsize >= 72:
            segname = data[cursor + 8 : cursor + 24].split(b"\x00", 1)[0].decode("utf-8", "ignore")
            if segname == LINKEDIT_SEGNAME:
                return {
                    "lc_offset": cursor,
                    "vmsize": struct.unpack_from("<Q", data, cursor + 32)[0],
                    "filesize": struct.unpack_from("<Q", data, cursor + 48)[0],
                }
        cursor += cmdsize
    return None


def _strip_code_signature(header, code_sig):
    ncmds = struct.unpack_from("<I", header, 16)[0]
    sizeofcmds = struct.unpack_from("<I", header, 20)[0]
    lc_end = MACH_HEADER_64_SIZE + sizeofcmds
    tail_start = code_sig["lc_offset"] + code_sig["cmdsize"]
    tail_len = lc_end - tail_start

    if tail_len > 0:
        header[code_sig["lc_offset"] : code_sig["lc_offset"] + tail_len] = header[tail_start:lc_end]
    header[lc_end - code_sig["cmdsize"] : lc_end] = b"\x00" * code_sig["cmdsize"]
    struct.pack_into("<I", header, 16, ncmds - 1)
    struct.pack_into("<I", header, 20, sizeofcmds - code_sig["cmdsize"])
