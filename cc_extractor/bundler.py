"""Repack extracted Bun modules into a standalone binary."""

import os
import json
import struct

from .bun_extract import parse_bun_binary
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
    manifest_path = os.path.join(indir, ".bundle_manifest.json")
    if not os.path.exists(manifest_path):
        raise ValueError(f"No .bundle_manifest.json found in {indir}")

    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read manifest {manifest_path}: {exc}") from exc

    print(f"[*] Packing {len(manifest.get('modules', []))} modules from {indir}...")

    try:
        with open(base_binary, "rb") as f:
            binary_data = f.read()
    except OSError as exc:
        raise ValueError(f"Cannot read base binary {base_binary}: {exc}") from exc
    info = parse_bun_binary(binary_data)
    new_raw_bytes, new_offsets_struct = _build_bundle_payload(indir, manifest)
    repacked = repack_binary(binary_data, info, new_raw_bytes, new_offsets_struct)

    try:
        with open(out_binary, "wb") as f:
            f.write(repacked.buf)
    except OSError as exc:
        raise ValueError(f"Cannot write output binary {out_binary}: {exc}") from exc

    print(f"[+] Successfully bundled to {out_binary}")


def _build_bundle_payload(indir, manifest):
    module_size = int(manifest.get("moduleSize", 52))
    # Bun v1.3.13+ uses 52-byte structs; earlier versions use 36-byte structs
    if module_size not in (36, 52):
        raise ValueError(f"Unsupported moduleSize in manifest: {module_size}")

    data_buffer = bytearray()
    module_structs = bytearray()

    # 1. Include execArgv if present
    argv_path = os.path.join(indir, "exec_argv.bin")
    exec_argv_offset = 0
    exec_argv_length = 0
    if manifest.get("execArgvLength", 0) > 0 and os.path.exists(argv_path):
        with open(argv_path, "rb") as f:
            argv_bytes = f.read()
        exec_argv_offset = len(data_buffer)
        exec_argv_length = len(argv_bytes)
        data_buffer.extend(argv_bytes)

    # 2. Iterate and append modules
    for mod in manifest.get("modules", []):
        name_bytes = mod["name"].encode("utf-8")
        name_off = len(data_buffer)
        name_len = len(name_bytes)
        data_buffer.extend(name_bytes)

        cont_off, cont_len = 0, 0
        if mod.get("sourceFile"):
            source_path = os.path.join(indir, mod["sourceFile"])
            if os.path.exists(source_path):
                with open(source_path, "rb") as f:
                    content_bytes = f.read()
                cont_off = len(data_buffer)
                cont_len = len(content_bytes)
                data_buffer.extend(content_bytes)

        smap_off, smap_len = 0, 0
        if mod.get("sourcemapFile"):
            smap_path = os.path.join(indir, mod["sourcemapFile"])
            if os.path.exists(smap_path):
                with open(smap_path, "rb") as f:
                    smap_bytes = f.read()
                smap_off = len(data_buffer)
                smap_len = len(smap_bytes)
                data_buffer.extend(smap_bytes)

        bc_off, bc_len = 0, 0
        if mod.get("bytecodeFile"):
            bc_path = os.path.join(indir, mod["bytecodeFile"])
            if os.path.exists(bc_path):
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

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Usage: bundler.py <indir> <out_binary> <base_binary>")
    else:
        pack_bundle(sys.argv[1], sys.argv[2], sys.argv[3])
