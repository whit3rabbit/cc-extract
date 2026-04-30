"""PE binary resize logic for the .bun section."""

import struct

from cc_extractor.bun_extract.constants import OFFSETS_SIZE, PE_DOS_MAGIC, PE_NT_SIGNATURE, TRAILER

SECTION_HEADER_SIZE = 40
NAME_BYTES = b".bun\x00"


class PeNotLastSectionError(Exception):
    """Raised when resizing .bun would overwrite a later PE section."""


def repack_pe(data, info, new_raw_bytes, new_offsets_struct):
    new_raw_bytes = bytes(new_raw_bytes)
    new_offsets_struct = bytes(new_offsets_struct)
    if len(new_offsets_struct) != OFFSETS_SIZE:
        raise ValueError(f"PE repack: offsets struct must be {OFFSETS_SIZE} bytes, got {len(new_offsets_struct)}")
    if info.section_offset is None:
        raise ValueError("PE repack: BunBinaryInfo missing section_offset")

    layout = _find_pe_layout(data)
    if layout is None:
        raise ValueError("PE repack: could not locate .bun section header")

    new_section_size = len(new_raw_bytes) + OFFSETS_SIZE + len(TRAILER)
    prefix = bytearray(data[: layout["bun_pointer_to_raw_data"]])
    struct.pack_into("<I", prefix, layout["bun_section_header_off"] + 16, new_section_size)
    struct.pack_into("<I", prefix, layout["bun_section_header_off"] + 8, new_section_size)
    return b"".join([bytes(prefix), new_raw_bytes, new_offsets_struct, TRAILER])


def _find_pe_layout(data):
    if len(data) < 0x40 or struct.unpack_from("<H", data, 0)[0] != PE_DOS_MAGIC:
        return None
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_off <= 0 or pe_off + 24 > len(data):
        return None
    if struct.unpack_from("<I", data, pe_off)[0] != PE_NT_SIGNATURE:
        return None

    num_sections = struct.unpack_from("<H", data, pe_off + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe_off + 20)[0]
    sections_start = pe_off + 24 + optional_size

    bun = None
    highest_ptr = -1
    highest_name = ""
    for index in range(num_sections):
        base = sections_start + index * SECTION_HEADER_SIZE
        if base + SECTION_HEADER_SIZE > len(data):
            return None
        ptr = struct.unpack_from("<I", data, base + 20)[0]
        size = struct.unpack_from("<I", data, base + 16)[0]
        name = data[base : base + 8].split(b"\x00", 1)[0].decode("utf-8", "ignore")
        if data[base : base + len(NAME_BYTES)] == NAME_BYTES:
            bun = {
                "bun_section_header_off": base,
                "bun_pointer_to_raw_data": ptr,
                "bun_size_of_raw_data": size,
            }
        if ptr > highest_ptr:
            highest_ptr = ptr
            highest_name = name

    if bun is None:
        return None
    if bun["bun_pointer_to_raw_data"] != highest_ptr:
        raise PeNotLastSectionError(
            f'.bun is not the last raw-data section (highest is "{highest_name}" '
            f'at {highest_ptr}; .bun is at {bun["bun_pointer_to_raw_data"]})'
        )
    return bun
