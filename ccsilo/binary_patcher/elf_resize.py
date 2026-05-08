"""ELF binary resize logic for the .bun section."""

import struct

from ccsilo.bun_extract.checked import checked_unpack_from as _checked_unpack_from
from ccsilo.bun_extract.constants import MACHO_SECTION_HEADER_SIZE, OFFSETS_SIZE, TRAILER
from ccsilo.bun_extract.types import BunFormatError

ELF_E_PHOFF = 32
ELF_E_SHOFF = 40
ELF_E_PHENTSIZE = 54
ELF_E_PHNUM = 56
ELF_E_SHENTSIZE = 58
ELF_E_SHNUM = 60
ELF_E_SHSTRNDX = 62

ELF_SH_NAME = 0
ELF_SH_OFFSET = 24
ELF_SH_SIZE = 32

PT_LOAD = 1
ELF_PH_TYPE = 0
ELF_PH_OFFSET = 8
ELF_PH_FILESZ = 32
ELF_PH_MEMSZ = 40

BUN_SECTION_NAME = ".bun"


def repack_elf(data, info, new_raw_bytes, new_offsets_struct):
    new_raw_bytes = bytes(new_raw_bytes)
    new_offsets_struct = bytes(new_offsets_struct)
    if len(new_offsets_struct) != OFFSETS_SIZE:
        raise ValueError(
            f"ELF repack: offsets struct must be {OFFSETS_SIZE} bytes, got {len(new_offsets_struct)}"
        )

    delta = len(new_raw_bytes) - info.byte_count
    tail_start = info.trailer_offset + len(TRAILER)
    if delta == 0:
        return b"".join(
            [
                data[: info.data_start],
                new_raw_bytes,
                new_offsets_struct,
                TRAILER,
                data[tail_start:],
            ]
        )

    prefix = bytearray(data[: info.data_start])
    tail = bytearray(data[tail_start:])
    old_section_table = _read_section_header_table(prefix) if tail else None

    if len(prefix) >= ELF_E_SHOFF + 8:
        _shift_u64_if_past(prefix, ELF_E_SHOFF, info.data_start, delta)
        _shift_u64_if_past(prefix, ELF_E_PHOFF, info.data_start, delta)
        _grow_pt_load_covering_section(prefix, info.data_start - MACHO_SECTION_HEADER_SIZE, delta)

    if tail:
        if old_section_table is not None:
            bun_header_off = _find_bun_section_header_offset(data, old_section_table)
            if bun_header_off is not None and bun_header_off >= tail_start:
                offset_within_tail = bun_header_off - tail_start
                if offset_within_tail + ELF_SH_SIZE + 8 <= len(tail):
                    old_size = _checked_unpack_from("<Q", tail, offset_within_tail + ELF_SH_SIZE, "ELF .bun section size")[0]
                    struct.pack_into("<Q", tail, offset_within_tail + ELF_SH_SIZE, old_size + delta)

        section_payload_start = info.data_start - MACHO_SECTION_HEADER_SIZE
        if 0 <= section_payload_start and section_payload_start + 8 <= len(prefix):
            old_inner = _checked_unpack_from("<Q", prefix, section_payload_start, "ELF .bun inner size")[0]
            struct.pack_into("<Q", prefix, section_payload_start, old_inner + delta)

    return b"".join([bytes(prefix), new_raw_bytes, new_offsets_struct, TRAILER, bytes(tail)])


def _shift_u64_if_past(header, field_offset, cutoff, delta):
    if field_offset + 8 > len(header):
        return
    original = _checked_unpack_from("<Q", header, field_offset, "ELF header offset field")[0]
    if original > cutoff:
        struct.pack_into("<Q", header, field_offset, original + delta)


def _read_section_header_table(header):
    if len(header) < ELF_E_SHSTRNDX + 2:
        return None
    try:
        file_off = _checked_unpack_from("<Q", header, ELF_E_SHOFF, "ELF section header table offset")[0]
        ent_size = _checked_unpack_from("<H", header, ELF_E_SHENTSIZE, "ELF section header entry size")[0]
        count = _checked_unpack_from("<H", header, ELF_E_SHNUM, "ELF section header count")[0]
        shstrndx = _checked_unpack_from("<H", header, ELF_E_SHSTRNDX, "ELF shstrndx")[0]
    except BunFormatError:
        return None
    if ent_size < ELF_SH_SIZE + 8 or count == 0:
        return None
    return {
        "file_off": file_off,
        "count": count,
        "ent_size": ent_size,
        "shstrndx": shstrndx,
    }


def _grow_pt_load_covering_section(prefix, section_payload_start, delta):
    phoff = _read_u64_or_zero(prefix, ELF_E_PHOFF)
    phentsize = _read_u16_or_zero(prefix, ELF_E_PHENTSIZE)
    phnum = _read_u16_or_zero(prefix, ELF_E_PHNUM)
    if phentsize < ELF_PH_MEMSZ + 8 or phoff + phnum * phentsize > len(prefix):
        return

    for index in range(phnum):
        offset = phoff + index * phentsize
        if _checked_unpack_from("<I", prefix, offset + ELF_PH_TYPE, f"ELF program header {index} type")[0] != PT_LOAD:
            continue
        ph_offset = _checked_unpack_from("<Q", prefix, offset + ELF_PH_OFFSET, f"ELF program header {index} offset")[0]
        ph_filesz = _checked_unpack_from("<Q", prefix, offset + ELF_PH_FILESZ, f"ELF program header {index} file size")[0]
        if ph_offset > section_payload_start or ph_offset + ph_filesz < section_payload_start:
            continue
        struct.pack_into("<Q", prefix, offset + ELF_PH_FILESZ, ph_filesz + delta)
        ph_memsz = _checked_unpack_from("<Q", prefix, offset + ELF_PH_MEMSZ, f"ELF program header {index} mem size")[0]
        struct.pack_into("<Q", prefix, offset + ELF_PH_MEMSZ, ph_memsz + delta)


def _find_bun_section_header_offset(data, table):
    if table["shstrndx"] >= table["count"]:
        return None
    shstr_header_off = table["file_off"] + table["shstrndx"] * table["ent_size"]
    if shstr_header_off + table["ent_size"] > len(data):
        return None
    try:
        shstr_off = _checked_unpack_from("<Q", data, shstr_header_off + ELF_SH_OFFSET, "ELF shstrtab offset")[0]
        shstr_size = _checked_unpack_from("<Q", data, shstr_header_off + ELF_SH_SIZE, "ELF shstrtab size")[0]
    except BunFormatError:
        return None
    if shstr_off + shstr_size > len(data):
        return None

    for index in range(table["count"]):
        header_off = table["file_off"] + index * table["ent_size"]
        if header_off + table["ent_size"] > len(data):
            return None
        name_index = _checked_unpack_from("<I", data, header_off + ELF_SH_NAME, f"ELF section {index} name index")[0]
        if name_index >= shstr_size:
            continue
        name_start = shstr_off + name_index
        name_end = data.find(b"\x00", name_start, shstr_off + shstr_size)
        if name_end < 0:
            continue
        if data[name_start:name_end].decode("utf-8", "ignore") == BUN_SECTION_NAME:
            return header_off
    return None


def _read_u64_or_zero(data, offset):
    try:
        return _checked_unpack_from("<Q", data, offset, "ELF u64 field")[0]
    except BunFormatError:
        return 0


def _read_u16_or_zero(data, offset):
    try:
        return _checked_unpack_from("<H", data, offset, "ELF u16 field")[0]
    except BunFormatError:
        return 0
