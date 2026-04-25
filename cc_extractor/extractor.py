import struct
import os
import json
from pathlib import Path
from .patcher import write_source_metadata

LC_SEGMENT_64 = 0x19
MACHO_MAGIC_64 = 0xFEEDFACF
MACHO_MAGIC_64_BE = 0xCFFAEDFE
TRAILER = b"\n---- Bun! ----\n"
SECTION_HEADER_SIZE = 8

def read_u32(data, offset, endian):
    return struct.unpack_from(endian + "I", data, offset)[0]

def read_u64(data, offset, endian):
    return struct.unpack_from(endian + "Q", data, offset)[0]

def find_bun_section_offset(binary_path):
    data = Path(binary_path).read_bytes()
    if len(data) < 32:
        raise ValueError("Binary too small to be Mach-O.")

    magic = struct.unpack_from("<I", data, 0)[0]
    if magic == MACHO_MAGIC_64:
        endian = "<"
    elif magic == MACHO_MAGIC_64_BE:
        endian = ">"
    else:
        raise ValueError("Unsupported binary format (expected Mach-O 64-bit).")

    ncmds = read_u32(data, 16, endian)
    offset = 32

    for _ in range(ncmds):
        cmd = read_u32(data, offset, endian)
        cmdsize = read_u32(data, offset + 4, endian)
        if cmd == LC_SEGMENT_64:
            segname_raw = data[offset + 8: offset + 24]
            segname = segname_raw.split(b"\x00", 1)[0].decode("utf-8", "ignore")
            nsects = read_u32(data, offset + 64, endian)
            sect_offset = offset + 72
            if segname == "__BUN":
                for _ in range(nsects):
                    sectname = data[sect_offset: sect_offset + 16].split(b"\x00", 1)[0].decode("utf-8", "ignore")
                    segname2 = data[sect_offset + 16: sect_offset + 32].split(b"\x00", 1)[0].decode("utf-8", "ignore")
                    size = read_u64(data, sect_offset + 40, endian)
                    fileoff = read_u32(data, sect_offset + 48, endian)
                    if segname2 == "__BUN" and sectname == "__bun":
                        return data, fileoff, size, endian
                    sect_offset += 80
        offset += cmdsize

    raise ValueError("Failed to locate __BUN,__bun section.")

def find_bun_section(binary_path):
    # For backward compatibility with existing patch_macho logic
    blob, fileoff, size, endian = find_bun_section_offset(binary_path)
    return blob[fileoff:fileoff + size], fileoff, size, endian

def extract_all(binary_path, out_dir, source_version=None):
    try:
        blob, section_offset, section_size, endian = find_bun_section_offset(binary_path)
        is_macho = True
    except ValueError as e:
        blob = Path(binary_path).read_bytes()
        section_offset = -1
        endian = "<"
        is_macho = False

    trailer_offset = blob.rfind(TRAILER)
    if trailer_offset == -1:
        raise ValueError("Could not find Bun trailer!")
    
    os_offset = trailer_offset - 32
    if os_offset < 0:
        raise ValueError("Invalid trailer offset, too close to beginning of file")
        
    byte_count = read_u64(blob, os_offset, endian)
    mod_offset = read_u32(blob, os_offset + 8, endian)
    mod_length = read_u32(blob, os_offset + 12, endian)
    entry_point_id = read_u32(blob, os_offset + 16, endian)
    exec_argv_offset = read_u32(blob, os_offset + 20, endian)
    exec_argv_length = read_u32(blob, os_offset + 24, endian)
    flags = read_u32(blob, os_offset + 28, endian)
    
    if section_offset >= 0:
        data_start = section_offset + SECTION_HEADER_SIZE
    else:
        # Based on user feedback: dataStart = trailerOffset - byteCount - OFFSETS_SIZE;
        data_start = trailer_offset - byte_count - 32
        
    MODULE_SIZE = 52
    num_modules = mod_length // MODULE_SIZE
    
    os.makedirs(out_dir, exist_ok=True)
    manifest = {
        "binaryPath": binary_path,
        "isMacho": is_macho,
        "entryPointId": entry_point_id,
        "execArgvOffset": exec_argv_offset,
        "execArgvLength": exec_argv_length,
        "flags": flags,
        "modules": []
    }
    
    if exec_argv_length > 0:
        argv_path = Path(out_dir) / "exec_argv.bin"
        argv_path.write_bytes(blob[data_start + exec_argv_offset : data_start + exec_argv_offset + exec_argv_length])
    
    for i in range(num_modules):
        base = data_start + mod_offset + i * MODULE_SIZE
        name_off = read_u32(blob, base, endian)
        name_len = read_u32(blob, base + 4, endian)
        cont_off = read_u32(blob, base + 8, endian)
        cont_len = read_u32(blob, base + 12, endian)
        smap_off = read_u32(blob, base + 16, endian)
        smap_len = read_u32(blob, base + 20, endian)
        bc_off = read_u32(blob, base + 24, endian)
        bc_len = read_u32(blob, base + 28, endian)
        padding_etc = blob[base + 32 : base + 48].hex()
        encoding = blob[base + 48]
        loader = blob[base + 49]
        mod_format = blob[base + 50]
        side = blob[base + 51]
        
        name = blob[data_start + name_off : data_start + name_off + name_len].decode("utf-8")
        
        rel_path = name
        if rel_path.startswith("/$bunfs/root/"):
            rel_path = rel_path[len("/$bunfs/root/"):]
        elif rel_path.startswith("$bunfs/root/"):
            rel_path = rel_path[len("$bunfs/root/"):]
            
        rel_path = rel_path.replace("..", "__")
        
        mod_info = {
            "index": i,
            "name": name,
            "rel_path": rel_path,
            "isEntry": i == entry_point_id,
            "sourceSize": cont_len,
            "bytecodeSize": bc_len,
            "sourcemapSize": smap_len,
            "paddingHex": padding_etc,
            "encoding": encoding,
            "loader": loader,
            "format": mod_format,
            "side": side,
        }
        
        out_path = Path(out_dir) / rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        if cont_len > 0:
            out_path.write_bytes(blob[data_start + cont_off : data_start + cont_off + cont_len])
            mod_info["sourceFile"] = rel_path
            
        if smap_len > 0:
            smap_path = Path(out_dir) / (rel_path + ".map")
            smap_path.write_bytes(blob[data_start + smap_off : data_start + smap_off + smap_len])
            mod_info["sourcemapFile"] = rel_path + ".map"
            
        if bc_len > 0:
            bc_path = Path(out_dir) / (rel_path + ".bc")
            bc_path.write_bytes(blob[data_start + bc_off : data_start + bc_off + bc_len])
            mod_info["bytecodeFile"] = rel_path + ".bc"
            
        manifest["modules"].append(mod_info)
        
    with open(os.path.join(out_dir, ".bundle_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    write_source_metadata(out_dir, binary_path, source_version=source_version)
        
    print(f"[+] Extracted {len(manifest['modules'])} modules to {out_dir}")
    return manifest

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: extractor.py <binary> <out_dir>")
    else:
        extract_all(sys.argv[1], sys.argv[2])
