import os
import json
import struct
from .macho import patch_macho
from .extractor import find_bun_section_offset

def pack_bundle(indir, out_binary, base_binary):
    manifest_path = os.path.join(indir, ".bundle_manifest.json")
    if not os.path.exists(manifest_path):
        raise ValueError(f"No .bundle_manifest.json found in {indir}")
        
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
        
    print(f"[*] Packing {len(manifest.get('modules', []))} modules from {indir}...")
    
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
                
        struct_data = struct.pack("<IIIIIIII",
            name_off, name_len,
            cont_off, cont_len,
            smap_off, smap_len,
            bc_off, bc_len
        )
        
        padding_hex = mod.get("paddingHex", "00" * 16)
        struct_data += bytes.fromhex(padding_hex)
        
        struct_data += struct.pack("BBBB", 
            mod["encoding"], 
            mod["loader"], 
            mod["format"], 
            mod["side"]
        )
        
        module_structs.extend(struct_data)
        
    mod_offset = len(data_buffer)
    mod_length = len(module_structs)
    byte_count = mod_offset + mod_length
    
    offsets_struct = struct.pack("<QIIIIII",
        byte_count,
        mod_offset,
        mod_length,
        manifest.get("entryPointId", 0),
        exec_argv_offset,
        exec_argv_length,
        manifest.get("flags", 0)
    )
    
    bundle_blob = bytearray()
    is_macho = manifest.get("isMacho", True)
    
    if is_macho:
        # Add the 8-byte u64 size header for Mach-O __BUN section
        macho_section_size = byte_count + 32 + 16 # data + offsets + trailer
        bundle_blob.extend(struct.pack("<Q", macho_section_size))
        
    bundle_blob.extend(data_buffer)
    bundle_blob.extend(module_structs)
    bundle_blob.extend(offsets_struct)
    bundle_blob.extend(b"\n---- Bun! ----\n")

    with open(base_binary, "rb") as f:
        binary_data = f.read()
    
    try:
        blob, fileoff, old_size, endian = find_bun_section_offset(base_binary)
        
        new_size = len(bundle_blob)
        if new_size <= old_size:
            print(f"[*] New bundle fits in old section (new: {new_size}, old: {old_size})")
            new_binary_data = bytearray(binary_data)
            new_binary_data[fileoff:fileoff + new_size] = bundle_blob
            new_binary_data[fileoff + new_size:fileoff + old_size] = b"\x00" * (old_size - new_size)
            with open(out_binary, "wb") as f:
                f.write(new_binary_data)
            patch_macho(out_binary, fileoff, new_size)
        else:
            print(f"[*] New bundle is larger ({new_size} > {old_size}). Appending to end of binary...")
            new_offset = len(binary_data)
            new_binary_data = bytearray(binary_data)
            new_binary_data.extend(bundle_blob)
            with open(out_binary, "wb") as f:
                f.write(new_binary_data)
            patch_macho(out_binary, new_offset, new_size)
    except ValueError:
        # If not Mach-O (e.g. Linux ELF), just append to the end or replace the existing appended block
        # For this prototype we'll try to find the old bundle and replace it
        print("[*] Base binary is not Mach-O. Attempting to replace trailer data...")
        trailer_offset = binary_data.rfind(b"\n---- Bun! ----\n")
        if trailer_offset != -1:
            os_offset = trailer_offset - 32
            old_byte_count = struct.unpack_from("<Q", binary_data, os_offset)[0]
            data_start = trailer_offset - old_byte_count - 32
            
            new_binary_data = bytearray(binary_data[:data_start])
            new_binary_data.extend(bundle_blob)
            with open(out_binary, "wb") as f:
                f.write(new_binary_data)
        else:
            print("[*] No existing bundle found, appending...")
            new_binary_data = bytearray(binary_data)
            new_binary_data.extend(bundle_blob)
            with open(out_binary, "wb") as f:
                f.write(new_binary_data)

    print(f"[+] Successfully bundled to {out_binary}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Usage: bundler.py <indir> <out_binary> <base_binary>")
    else:
        pack_bundle(sys.argv[1], sys.argv[2], sys.argv[3])
