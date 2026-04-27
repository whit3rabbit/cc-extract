import struct

from cc_extractor.bun_extract.constants import MACHO_SECTION_HEADER_SIZE, OFFSETS_SIZE, TRAILER

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
    if len(prefix) >= ELF_E_SHOFF + 8:
        _shift_u64_if_past(prefix, ELF_E_SHOFF, info.data_start, delta)
        _shift_u64_if_past(prefix, ELF_E_PHOFF, info.data_start, delta)
        _grow_pt_load_covering_section(prefix, info.data_start - MACHO_SECTION_HEADER_SIZE, delta)

    tail = bytearray(data[tail_start:])
    if tail:
        table = _read_section_header_table(prefix)
        if table is not None:
            bun_header_off = _find_bun_section_header_offset(data, table)
            if bun_header_off is not None and bun_header_off >= tail_start:
                offset_within_tail = bun_header_off - tail_start
                if offset_within_tail + ELF_SH_SIZE + 8 <= len(tail):
                    old_size = struct.unpack_from("<Q", tail, offset_within_tail + ELF_SH_SIZE)[0]
                    struct.pack_into("<Q", tail, offset_within_tail + ELF_SH_SIZE, old_size + delta)

        section_payload_start = info.data_start - MACHO_SECTION_HEADER_SIZE
        if 0 <= section_payload_start and section_payload_start + 8 <= len(prefix):
            old_inner = struct.unpack_from("<Q", prefix, section_payload_start)[0]
            struct.pack_into("<Q", prefix, section_payload_start, old_inner + delta)

    return b"".join([bytes(prefix), new_raw_bytes, new_offsets_struct, TRAILER, bytes(tail)])


def _shift_u64_if_past(header, field_offset, cutoff, delta):
    if field_offset + 8 > len(header):
        return
    original = struct.unpack_from("<Q", header, field_offset)[0]
    if original > cutoff:
        struct.pack_into("<Q", header, field_offset, original + delta)


def _read_section_header_table(header):
    if len(header) < ELF_E_SHSTRNDX + 2:
        return None
    file_off = struct.unpack_from("<Q", header, ELF_E_SHOFF)[0]
    ent_size = struct.unpack_from("<H", header, ELF_E_SHENTSIZE)[0]
    count = struct.unpack_from("<H", header, ELF_E_SHNUM)[0]
    shstrndx = struct.unpack_from("<H", header, ELF_E_SHSTRNDX)[0]
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
        if struct.unpack_from("<I", prefix, offset + ELF_PH_TYPE)[0] != PT_LOAD:
            continue
        ph_offset = struct.unpack_from("<Q", prefix, offset + ELF_PH_OFFSET)[0]
        ph_filesz = struct.unpack_from("<Q", prefix, offset + ELF_PH_FILESZ)[0]
        if ph_offset > section_payload_start or ph_offset + ph_filesz < section_payload_start:
            continue
        struct.pack_into("<Q", prefix, offset + ELF_PH_FILESZ, ph_filesz + delta)
        ph_memsz = struct.unpack_from("<Q", prefix, offset + ELF_PH_MEMSZ)[0]
        struct.pack_into("<Q", prefix, offset + ELF_PH_MEMSZ, ph_memsz + delta)


def _find_bun_section_header_offset(data, table):
    if table["shstrndx"] >= table["count"]:
        return None
    shstr_header_off = table["file_off"] + table["shstrndx"] * table["ent_size"]
    if shstr_header_off + table["ent_size"] > len(data):
        return None
    shstr_off = struct.unpack_from("<Q", data, shstr_header_off + ELF_SH_OFFSET)[0]
    shstr_size = struct.unpack_from("<Q", data, shstr_header_off + ELF_SH_SIZE)[0]
    if shstr_off + shstr_size > len(data):
        return None

    for index in range(table["count"]):
        header_off = table["file_off"] + index * table["ent_size"]
        if header_off + table["ent_size"] > len(data):
            return None
        name_index = struct.unpack_from("<I", data, header_off + ELF_SH_NAME)[0]
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
    if offset + 8 > len(data):
        return 0
    return struct.unpack_from("<Q", data, offset)[0]


def _read_u16_or_zero(data, offset):
    if offset + 2 > len(data):
        return 0
    return struct.unpack_from("<H", data, offset)[0]
