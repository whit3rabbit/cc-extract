import struct

from .constants import (
    BUNFS_PATH_PREFIXES,
    ENCODING_NAMES,
    FLAG_OFFSETS_BY_SIZE,
    FORMAT_NAMES,
    LOADER_NAMES,
    MODULE_SIZE_V52,
    MODULE_SIZES,
    OFFSETS_SIZE,
    TRAILER,
    TRAILER_SEARCH_WINDOW,
)
from .elf import elf_data_start, is_elf
from .macho import find_bun_section, is_macho, macho_data_start
from .pe import find_bun_pe_section, is_pe, pe_data_start
from .types import BunBinaryInfo, BunFormatError, BunModule


def parse_bun_binary(data):
    trailer_offset = _find_trailer(data)
    if trailer_offset < 0:
        raise BunFormatError(
            'Bun trailer "\\n---- Bun! ----\\n" not found in last '
            f"{TRAILER_SEARCH_WINDOW} bytes"
        )

    offsets_start = trailer_offset - OFFSETS_SIZE
    if offsets_start < 0:
        raise BunFormatError(f"Trailer at offset {trailer_offset} leaves no room for Offsets struct")

    byte_count = struct.unpack_from("<Q", data, offsets_start)[0]
    modules_off = struct.unpack_from("<I", data, offsets_start + 8)[0]
    modules_len = struct.unpack_from("<I", data, offsets_start + 12)[0]
    entry_point_id = struct.unpack_from("<I", data, offsets_start + 16)[0]
    flags = struct.unpack_from("<I", data, offsets_start + 28)[0]

    platform, data_start, section_offset, section_size, has_code_signature = _locate_payload(
        data,
        trailer_offset,
        byte_count,
    )

    if data_start < 0 or data_start + byte_count > len(data):
        raise BunFormatError(
            f"Computed dataStart={data_start} byteCount={byte_count} is out of range "
            f"for binary of length {len(data)}"
        )

    parsed = None
    errors = []
    for module_size in MODULE_SIZES:
        if modules_len % module_size != 0:
            errors.append(f"size={module_size}: modulesLen={modules_len} not divisible")
            continue
        try:
            modules = _read_module_table(
                data,
                data_start,
                modules_off,
                modules_len,
                module_size,
                entry_point_id,
                byte_count,
            )
            parsed = (module_size, modules)
            break
        except ValueError as exc:
            errors.append(f"size={module_size}: {exc}")

    if parsed is None:
        raise BunFormatError(
            "Could not parse module table at any known struct size. "
            f"Attempts: {'; '.join(errors)}"
        )

    module_size, modules = parsed
    return BunBinaryInfo(
        platform=platform,
        data_start=data_start,
        trailer_offset=trailer_offset,
        byte_count=byte_count,
        module_size=module_size,
        modules=modules,
        entry_point_id=entry_point_id,
        flags=flags,
        section_offset=section_offset,
        section_size=section_size,
        has_code_signature=has_code_signature,
        bun_version_hint=">=1.3.13" if module_size == MODULE_SIZE_V52 else "pre-1.3.13",
    )


def _locate_payload(data, trailer_offset, byte_count):
    section_offset = None
    section_size = None
    has_code_signature = False

    if is_macho(data):
        section = find_bun_section(data)
        if section is not None:
            section_offset = section.section_offset
            section_size = section.section_size
            has_code_signature = section.has_code_signature
            return "macho", macho_data_start(section.section_offset), section_offset, section_size, has_code_signature
        return "macho", elf_data_start(trailer_offset, byte_count), section_offset, section_size, has_code_signature

    if is_pe(data):
        section = find_bun_pe_section(data)
        if section is not None:
            section_offset = section.pointer_to_raw_data
            section_size = section.size_of_raw_data
            return "pe", pe_data_start(section.pointer_to_raw_data), section_offset, section_size, has_code_signature
        return "pe", elf_data_start(trailer_offset, byte_count), section_offset, section_size, has_code_signature

    if is_elf(data):
        return "elf", elf_data_start(trailer_offset, byte_count), section_offset, section_size, has_code_signature

    return "elf", elf_data_start(trailer_offset, byte_count), section_offset, section_size, has_code_signature


def _find_trailer(data):
    min_start = max(0, len(data) - TRAILER_SEARCH_WINDOW)
    return data.rfind(TRAILER, min_start)


def _read_module_table(data, data_start, modules_off, modules_len, module_size, entry_point_id, byte_count):
    module_count = modules_len // module_size
    flags_base = FLAG_OFFSETS_BY_SIZE[module_size]
    modules = []

    for index in range(module_count):
        base = data_start + modules_off + index * module_size
        if base + module_size > len(data):
            raise ValueError(f"module {index} extends past EOF")

        name_off = struct.unpack_from("<I", data, base)[0]
        name_len = struct.unpack_from("<I", data, base + 4)[0]
        cont_off = struct.unpack_from("<I", data, base + 8)[0]
        cont_len = struct.unpack_from("<I", data, base + 12)[0]
        smap_off = struct.unpack_from("<I", data, base + 16)[0]
        smap_len = struct.unpack_from("<I", data, base + 20)[0]
        bc_off = struct.unpack_from("<I", data, base + 24)[0]
        bc_len = struct.unpack_from("<I", data, base + 28)[0]

        if name_len == 0 or name_len > 4096:
            raise ValueError(f"module {index} has implausible nameLen={name_len}")
        if name_off + name_len > byte_count:
            raise ValueError(f"module {index} name extends past byteCount")
        if cont_off + cont_len > byte_count:
            raise ValueError(f"module {index} content extends past byteCount")
        if smap_off + smap_len > byte_count:
            raise ValueError(f"module {index} sourcemap extends past byteCount")
        if bc_off + bc_len > byte_count:
            raise ValueError(f"module {index} bytecode extends past byteCount")

        name_bytes = data[data_start + name_off : data_start + name_off + name_len]
        if not _is_plausible_name_bytes(name_bytes):
            raise ValueError(f"module {index} name is not a plausible path")

        enc_byte = data[base + flags_base]
        loader_byte = data[base + flags_base + 1]
        format_byte = data[base + flags_base + 2]
        side_byte = data[base + flags_base + 3]

        modules.append(
            BunModule(
                index=index,
                name=_strip_bunfs(name_bytes.decode("utf-8")),
                cont_off=cont_off,
                cont_len=cont_len,
                smap_off=smap_off,
                smap_len=smap_len,
                bc_off=bc_off,
                bc_len=bc_len,
                encoding=ENCODING_NAMES.get(enc_byte, enc_byte),
                loader=LOADER_NAMES.get(loader_byte, loader_byte),
                format=FORMAT_NAMES.get(format_byte, format_byte),
                side="client" if side_byte == 1 else "server",
                is_entry=index == entry_point_id,
            )
        )

    return modules


def _strip_bunfs(raw):
    for prefix in BUNFS_PATH_PREFIXES:
        if raw.startswith(prefix):
            return raw[len(prefix) :]
    return raw


def _is_plausible_name_bytes(value):
    if not value:
        return False
    for byte in value:
        if byte == 0:
            return False
        if byte < 0x20 and byte != 0x09:
            return False
        if byte == 0x7F:
            return False
    return True
