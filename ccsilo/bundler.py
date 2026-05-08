"""Repack extracted Bun modules into a standalone binary."""

import struct
from dataclasses import dataclass
from pathlib import Path

from ._utils import read_json_strict, safe_child_path
from .bun_extract import parse_bun_binary
from .bun_extract.checked import checked_slice as _checked_slice
from .bun_extract.checked import checked_unpack_from as _checked_unpack_from
from .bun_extract.constants import OFFSETS_SIZE
from .binary_patcher import repack_binary

ENCODING_IDS = {
    "binary": 0,
    "latin1": 1,
    "utf8": 2,
}

LOADER_IDS = {
    "file": 0,
    "js": 1,
    "wasm": 9,
    "napi": 10,
}

FORMAT_IDS = {
    "none": 0,
    "esm": 1,
    "cjs": 2,
}

SIDE_IDS = {
    "server": 0,
    "client": 1,
}

def pack_bundle(indir, out_binary, base_binary):
    """Pack extracted modules and manifest back into a standalone binary."""
    in_root = Path(indir).resolve()
    manifest_path = in_root / ".bundle_manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"No .bundle_manifest.json found in {indir}")

    try:
        manifest = read_json_strict(manifest_path)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot read manifest {manifest_path}: {exc}") from exc

    print(f"[*] Packing {len(manifest.get('modules', []))} modules from {indir}...")

    try:
        with open(base_binary, "rb") as f:
            binary_data = f.read()
    except OSError as exc:
        raise ValueError(f"Cannot read base binary {base_binary}: {exc}") from exc
    info = parse_bun_binary(binary_data)
    if _can_repack_from_base(manifest, info):
        new_raw_bytes, new_offsets_struct = _build_bundle_payload_from_base(in_root, manifest, binary_data, info)
    else:
        new_raw_bytes, new_offsets_struct = _build_bundle_payload(in_root, manifest)
    repacked = repack_binary(binary_data, info, new_raw_bytes, new_offsets_struct)

    try:
        with open(out_binary, "wb") as f:
            f.write(repacked.buf)
    except OSError as exc:
        raise ValueError(f"Cannot write output binary {out_binary}: {exc}") from exc

    print(f"[+] Successfully bundled to {out_binary}")


def _build_bundle_payload(indir, manifest):
    in_root = Path(indir)
    module_size = int(manifest.get("moduleSize", 52))
    # Bun v1.3.13+ uses 52-byte structs; earlier versions use 36-byte structs
    if module_size not in (36, 52):
        raise ValueError(f"Unsupported moduleSize in manifest: {module_size}")

    data_buffer = bytearray()
    module_structs = bytearray()

    # 1. Include execArgv if present
    argv_path = in_root / "exec_argv.bin"
    exec_argv_offset = 0
    exec_argv_length = 0
    if manifest.get("execArgvLength", 0) > 0 and argv_path.exists():
        with open(argv_path, "rb") as f:
            argv_bytes = f.read()
        exec_argv_offset = len(data_buffer)
        exec_argv_length = len(argv_bytes)
        data_buffer.extend(argv_bytes)

    # 2. Iterate and append modules
    for index, mod in enumerate(manifest.get("modules", [])):
        name_bytes = _module_raw_name(mod).encode("utf-8")
        name_off = len(data_buffer)
        name_len = len(name_bytes)
        data_buffer.extend(name_bytes)

        cont_off, cont_len = 0, 0
        if mod.get("sourceFile"):
            source_path = _manifest_child_path(in_root, mod["sourceFile"], f"modules[{index}].sourceFile")
            if source_path.exists():
                with open(source_path, "rb") as f:
                    content_bytes = f.read()
                cont_off = len(data_buffer)
                cont_len = len(content_bytes)
                data_buffer.extend(content_bytes)

        smap_off, smap_len = 0, 0
        if mod.get("sourcemapFile"):
            smap_path = _manifest_child_path(in_root, mod["sourcemapFile"], f"modules[{index}].sourcemapFile")
            if smap_path.exists():
                with open(smap_path, "rb") as f:
                    smap_bytes = f.read()
                smap_off = len(data_buffer)
                smap_len = len(smap_bytes)
                data_buffer.extend(smap_bytes)

        bc_off, bc_len = 0, 0
        if mod.get("bytecodeFile"):
            bc_path = _manifest_child_path(in_root, mod["bytecodeFile"], f"modules[{index}].bytecodeFile")
            if bc_path.exists():
                with open(bc_path, "rb") as f:
                    bc_bytes = f.read()
                bc_off = len(data_buffer)
                bc_len = len(bc_bytes)
                data_buffer.extend(bc_bytes)

        module_structs.extend(
            _build_module_struct(
                module_size,
                mod,
                name_off,
                name_len,
                cont_off,
                cont_len,
                smap_off,
                smap_len,
                bc_off,
                bc_len,
            )
        )

    mod_offset = len(data_buffer)
    mod_length = len(module_structs)
    byte_count = mod_offset + mod_length

    offsets_struct = struct.pack(
        "<QIIIIII",
        byte_count,
        mod_offset,
        mod_length,
        manifest.get("entryPointId", 0),
        exec_argv_offset,
        exec_argv_length,
        manifest.get("flags", 0),
    )
    return bytes(data_buffer + module_structs), offsets_struct


@dataclass(frozen=True)
class _Replacement:
    module_index: int
    slot: int
    old_off: int
    old_len: int
    new_bytes: bytes


def _can_repack_from_base(manifest, info):
    if int(manifest.get("moduleSize", info.module_size)) != info.module_size:
        return False
    modules = manifest.get("modules", [])
    if len(modules) != len(info.modules):
        return False
    required = (
        "nameOffset",
        "nameSize",
        "contentOffset",
        "sourceSize",
        "sourcemapOffset",
        "sourcemapSize",
        "bytecodeOffset",
        "bytecodeSize",
    )
    for index, (mod, base_mod) in enumerate(zip(modules, info.modules)):
        if int(mod.get("index", index)) != index:
            return False
        if mod.get("name") != base_mod.name:
            return False
        if any(field not in mod for field in required):
            return False
    return True


def _build_bundle_payload_from_base(indir, manifest, binary_data, info):
    in_root = Path(indir)
    offsets_start = info.trailer_offset - OFFSETS_SIZE
    old_byte_count = _checked_unpack_from("<Q", binary_data, offsets_start, "pack byteCount")[0]
    old_modules_off = _checked_unpack_from("<I", binary_data, offsets_start + 8, "pack modulesOffset")[0]
    old_modules_len = _checked_unpack_from("<I", binary_data, offsets_start + 12, "pack modulesLength")[0]
    old_exec_argv_offset = _checked_unpack_from("<I", binary_data, offsets_start + 20, "pack execArgvOffset")[0]
    old_exec_argv_length = _checked_unpack_from("<I", binary_data, offsets_start + 24, "pack execArgvLength")[0]
    old_flags = _checked_unpack_from("<I", binary_data, offsets_start + 28, "pack flags")[0]

    old_raw = _checked_slice(binary_data, info.data_start, old_byte_count, "pack raw Bun payload")
    replacements = _collect_replacements(in_root, manifest, info)
    new_raw = _apply_replacements(old_raw, replacements)
    shift_at = _shift_function(replacements)
    new_modules_off = shift_at(old_modules_off)

    for index, _mod in enumerate(manifest.get("modules", [])):
        base = new_modules_off + index * info.module_size
        if base + info.module_size > len(new_raw):
            raise ValueError(f"module table entry {index} extends past rebuilt payload")
        for slot in (0, 8, 16, 24):
            old_ptr = _checked_unpack_from(
                "<I",
                old_raw,
                old_modules_off + index * info.module_size + slot,
                f"pack module {index} pointer",
            )[0]
            old_len = _checked_unpack_from(
                "<I",
                old_raw,
                old_modules_off + index * info.module_size + slot + 4,
                f"pack module {index} length",
            )[0]
            replacement = _find_replacement(replacements, index, slot)
            if replacement is None:
                new_ptr = shift_at(old_ptr) if old_len else old_ptr
                new_len = old_len
            else:
                new_ptr = shift_at(replacement.old_off)
                new_len = len(replacement.new_bytes)
            struct.pack_into("<I", new_raw, base + slot, new_ptr)
            struct.pack_into("<I", new_raw, base + slot + 4, new_len)

    if old_exec_argv_length:
        exec_argv_offset = shift_at(old_exec_argv_offset)
    elif old_exec_argv_offset == old_byte_count - 1:
        exec_argv_offset = len(new_raw) - 1
    else:
        exec_argv_offset = old_exec_argv_offset

    offsets_struct = struct.pack(
        "<QIIIIII",
        len(new_raw),
        new_modules_off,
        old_modules_len,
        int(manifest.get("entryPointId", info.entry_point_id)),
        exec_argv_offset,
        old_exec_argv_length,
        int(manifest.get("flags", old_flags)),
    )
    return bytes(new_raw), offsets_struct


def _collect_replacements(in_root, manifest, info):
    replacements = []
    for index, (mod, base_mod) in enumerate(zip(manifest.get("modules", []), info.modules)):
        raw_name = _module_raw_name(mod).encode("utf-8")
        replacements.append(_Replacement(index, 0, base_mod.name_off, base_mod.name_len, raw_name))

        if mod.get("sourceFile"):
            source_path = _manifest_child_path(in_root, mod["sourceFile"], f"modules[{index}].sourceFile")
            if source_path.exists():
                replacements.append(_Replacement(index, 8, base_mod.cont_off, base_mod.cont_len, source_path.read_bytes()))

        if mod.get("sourcemapFile"):
            smap_path = _manifest_child_path(in_root, mod["sourcemapFile"], f"modules[{index}].sourcemapFile")
            if smap_path.exists():
                replacements.append(_Replacement(index, 16, base_mod.smap_off, base_mod.smap_len, smap_path.read_bytes()))

        if mod.get("bytecodeFile"):
            bc_path = _manifest_child_path(in_root, mod["bytecodeFile"], f"modules[{index}].bytecodeFile")
            if bc_path.exists():
                replacements.append(_Replacement(index, 24, base_mod.bc_off, base_mod.bc_len, bc_path.read_bytes()))

    return sorted(replacements, key=lambda replacement: (replacement.old_off, replacement.slot, replacement.module_index))


def _apply_replacements(old_raw, replacements):
    new_raw = bytearray()
    cursor = 0
    for replacement in replacements:
        if replacement.old_len < 0:
            raise ValueError("replacement length cannot be negative")
        if replacement.old_off < cursor:
            raise ValueError("manifest replacement ranges overlap")
        if replacement.old_off + replacement.old_len > len(old_raw):
            raise ValueError("manifest replacement range extends past payload")
        new_raw.extend(old_raw[cursor : replacement.old_off])
        new_raw.extend(replacement.new_bytes)
        cursor = replacement.old_off + replacement.old_len
    new_raw.extend(old_raw[cursor:])
    return new_raw


def _shift_function(replacements):
    checkpoints = []
    delta = 0
    for replacement in replacements:
        checkpoints.append((replacement.old_off, delta))
        delta += len(replacement.new_bytes) - replacement.old_len
        checkpoints.append((replacement.old_off + replacement.old_len, delta))

    def shift(old_off):
        current = 0
        for checkpoint, checkpoint_delta in checkpoints:
            if old_off < checkpoint:
                break
            current = checkpoint_delta
        return old_off + current

    return shift


def _find_replacement(replacements, module_index, slot):
    for replacement in replacements:
        if replacement.module_index == module_index and replacement.slot == slot:
            return replacement
    return None


def _module_raw_name(mod):
    return str(mod.get("rawName") or mod["name"])


def _build_module_struct(
    module_size,
    mod,
    name_off,
    name_len,
    cont_off,
    cont_len,
    smap_off,
    smap_len,
    bc_off,
    bc_len,
):
    struct_data = bytearray(module_size)
    struct.pack_into("<IIIIIIII", struct_data, 0, name_off, name_len, cont_off, cont_len, smap_off, smap_len, bc_off, bc_len)

    # 52-byte structs have 16 bytes of padding between offsets and flags
    if module_size == 52:
        padding = bytes.fromhex(mod.get("paddingHex", "00" * 16))
        struct_data[32:48] = padding[:16].ljust(16, b"\x00")
        flags_base = 48
    else:
        flags_base = 32

    # Four single-byte flag fields packed after the 8 offset/name pairs
    struct_data[flags_base : flags_base + 4] = bytes(
        [
            _flag_byte(mod.get("encoding", 2), ENCODING_IDS, "encoding"),
            _flag_byte(mod.get("loader", 1), LOADER_IDS, "loader"),
            _flag_byte(mod.get("format", 1), FORMAT_IDS, "format"),
            _flag_byte(mod.get("side", 0), SIDE_IDS, "side"),
        ]
    )
    return bytes(struct_data)


def _flag_byte(value, lookup, field_name):
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value in lookup:
        return lookup[value]
    raise ValueError(f"Invalid module {field_name} flag: {value!r}")


def _manifest_child_path(root: Path, rel_path, label: str) -> Path:
    try:
        return safe_child_path(root, rel_path, label=label)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Usage: bundler.py <indir> <out_binary> <base_binary>")
    else:
        pack_bundle(sys.argv[1], sys.argv[2], sys.argv[3])
