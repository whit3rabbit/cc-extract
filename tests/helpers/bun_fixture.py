import struct

from cc_extractor.bun_extract.constants import OFFSETS_SIZE, TRAILER


def build_bun_fixture(
    platform="elf",
    module_struct_size=52,
    modules=None,
    entry_point_id=0,
    flags=0,
    with_code_signature=False,
    trailing_padding=0,
):
    modules = modules or []
    table_info = _build_raw_bytes_and_table(module_struct_size, modules)
    offsets = _build_offsets_struct(table_info, entry_point_id, flags)

    if platform == "elf":
        return _build_elf(table_info, offsets)
    if platform == "macho":
        return _build_macho(table_info, offsets, with_code_signature, trailing_padding)
    if platform == "pe":
        return _build_pe(table_info, offsets)
    raise ValueError(f"Unsupported fixture platform: {platform}")


def _to_bytes(value):
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")


def _build_raw_bytes_and_table(module_struct_size, modules):
    flags_base = 32 if module_struct_size == 36 else 48
    data = bytearray()
    packed = []

    def append(value):
        offset = len(data)
        data.extend(value)
        return offset

    for module in modules:
        name = _to_bytes(module["name"])
        content = _to_bytes(module.get("content", b""))
        sourcemap = _to_bytes(module.get("sourcemap", b""))
        bytecode = _to_bytes(module.get("bytecode", b""))

        name_off = append(name)
        cont_off = append(content)
        smap_off = append(sourcemap) if sourcemap else 0
        bc_off = append(bytecode) if bytecode else 0

        packed.append(
            {
                "name_off": name_off,
                "name_len": len(name),
                "cont_off": cont_off,
                "cont_len": len(content),
                "smap_off": smap_off,
                "smap_len": len(sourcemap),
                "bc_off": bc_off,
                "bc_len": len(bytecode),
                "flags": (
                    module.get("encoding", 2),
                    module.get("loader", 1),
                    module.get("format", 1),
                    module.get("side", 0),
                ),
            }
        )

    modules_off = len(data)
    modules_len = len(packed) * module_struct_size
    table = bytearray(modules_len)

    for index, module in enumerate(packed):
        base = index * module_struct_size
        _write_string_pointer(table, base, module["name_off"], module["name_len"])
        _write_string_pointer(table, base + 8, module["cont_off"], module["cont_len"])
        _write_string_pointer(table, base + 16, module["smap_off"], module["smap_len"])
        _write_string_pointer(table, base + 24, module["bc_off"], module["bc_len"])
        table[base + flags_base : base + flags_base + 4] = bytes(module["flags"])

    data.extend(table)
    return {
        "raw_bytes": bytes(data),
        "byte_count": len(data),
        "modules_off": modules_off,
        "modules_len": modules_len,
    }


def _write_string_pointer(buffer, base, offset, length):
    struct.pack_into("<I", buffer, base, offset)
    struct.pack_into("<I", buffer, base + 4, length)


def _build_offsets_struct(table_info, entry_point_id, flags):
    offsets = bytearray(OFFSETS_SIZE)
    struct.pack_into("<Q", offsets, 0, table_info["byte_count"])
    struct.pack_into("<I", offsets, 8, table_info["modules_off"])
    struct.pack_into("<I", offsets, 12, table_info["modules_len"])
    struct.pack_into("<I", offsets, 16, entry_point_id)
    struct.pack_into("<I", offsets, 28, flags)
    return bytes(offsets)


def _build_elf(table_info, offsets):
    header = bytearray(64)
    header[:4] = b"\x7fELF"
    data_start = len(header)
    buf = bytes(header) + table_info["raw_bytes"] + offsets + TRAILER
    return {
        "platform": "elf",
        "buf": buf,
        "expected": {"data_start": data_start},
    }


def _build_macho(table_info, offsets, with_code_signature, trailing_padding):
    header = bytearray(4096)
    struct.pack_into("<I", header, 0, 0xFEEDFACF)

    if with_code_signature:
        struct.pack_into("<I", header, 16, 1)
        struct.pack_into("<I", header, 20, 16)
        struct.pack_into("<I", header, 32, 0x1D)
        struct.pack_into("<I", header, 36, 16)

    section_header_off = 256
    header[section_header_off : section_header_off + 16] = b"__bun\x00" + (b"\x00" * 10)
    header[section_header_off + 16 : section_header_off + 32] = b"__BUN\x00" + (b"\x00" * 10)

    section_offset = len(header)
    section_data_len = len(table_info["raw_bytes"]) + OFFSETS_SIZE + len(TRAILER)
    struct.pack_into("<Q", header, section_header_off + 40, section_data_len)
    struct.pack_into("<I", header, section_header_off + 48, section_offset)

    size_header = bytearray(8)
    struct.pack_into("<Q", size_header, 0, len(table_info["raw_bytes"]))
    padding = b"\x00" * trailing_padding
    buf = bytes(header) + bytes(size_header) + table_info["raw_bytes"] + offsets + TRAILER + padding
    return {
        "platform": "macho",
        "buf": buf,
        "expected": {
            "data_start": section_offset + 8,
            "section_offset": section_offset,
        },
    }


def _build_pe(table_info, offsets):
    dos = bytearray(64)
    struct.pack_into("<H", dos, 0, 0x5A4D)
    pe_offset = 0x80
    struct.pack_into("<I", dos, 0x3C, pe_offset)

    nt_prefix = bytes(pe_offset - len(dos))
    coff = bytearray(24)
    struct.pack_into("<I", coff, 0, 0x00004550)
    struct.pack_into("<H", coff, 6, 1)
    struct.pack_into("<H", coff, 20, 0)

    section_header = bytearray(40)
    section_header[:5] = b".bun\x00"
    header = bytearray(bytes(dos) + nt_prefix + bytes(coff) + bytes(section_header))

    pointer_to_raw_data = len(header)
    size_of_raw_data = len(table_info["raw_bytes"]) + OFFSETS_SIZE + len(TRAILER)
    section_base = pe_offset + 24
    struct.pack_into("<I", header, section_base + 16, size_of_raw_data)
    struct.pack_into("<I", header, section_base + 20, pointer_to_raw_data)

    buf = bytes(header) + table_info["raw_bytes"] + offsets + TRAILER
    return {
        "platform": "pe",
        "buf": buf,
        "expected": {
            "data_start": pointer_to_raw_data,
            "pointer_to_raw_data": pointer_to_raw_data,
        },
    }
