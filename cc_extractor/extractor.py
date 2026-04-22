import struct
import os
import json
from pathlib import Path
from .patcher import write_source_metadata

LC_SEGMENT_64 = 0x19
MACHO_MAGIC_64 = 0xFEEDFACF
MACHO_MAGIC_64_BE = 0xCFFAEDFE

def read_u32(data, offset, endian):
    return struct.unpack_from(endian + "I", data, offset)[0]

def read_u64(data, offset, endian):
    return struct.unpack_from(endian + "Q", data, offset)[0]

def find_bun_section(binary_path):
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
            # segname is at offset + 8, length 16
            segname_raw = data[offset + 8: offset + 24]
            segname = segname_raw.split(b"\x00", 1)[0].decode("utf-8", "ignore")
            # nsects is at offset + 64
            nsects = read_u32(data, offset + 64, endian)
            sect_offset = offset + 72
            if segname == "__BUN":
                for _ in range(nsects):
                    sectname = data[sect_offset: sect_offset + 16].split(b"\x00", 1)[0].decode("utf-8", "ignore")
                    segname2 = data[sect_offset + 16: sect_offset + 32].split(b"\x00", 1)[0].decode("utf-8", "ignore")
                    size = read_u64(data, sect_offset + 40, endian)
                    fileoff = read_u32(data, sect_offset + 48, endian)
                    if segname2 == "__BUN" and sectname == "__bun":
                        return data[fileoff:fileoff + size], fileoff, size, endian
                    sect_offset += 80
        offset += cmdsize

    raise ValueError("Failed to locate __BUN,__bun section.")

def iter_bun_paths(blob):
    prefixes = [b"file:///", b"/$bunfs/root/"]
    v2_sig = b"\xfa\xf9\x0d\x04"
    
    for prefix in prefixes:
        start = 0
        while True:
            idx = blob.find(prefix, start)
            if idx == -1:
                break
            
            if idx >= 4:
                length = struct.unpack_from("<I", blob, idx - 4)[0]
                if 1 < length < 1024:
                    end = idx + length
                    raw_path = blob[idx:end]
                    path_str = raw_path.decode("utf-8", "ignore")
                    if "\x00" not in path_str:
                         yield path_str, idx, end, prefix
            start = idx + len(prefix)

def get_entry(blob, path_end):
    cursor = path_end
    # V2 signature?
    if cursor + 22 <= len(blob) and blob[cursor:cursor+4] == b"\xfa\xf9\x0d\x04":
        # we want to keep the 22 bytes of metadata
        metadata = blob[cursor:cursor+22]
        size = struct.unpack_from("<I", metadata, 18)[0]
        data_start = cursor + 22
        return data_start, size, metadata, "v2"

    # V1 (skip optional zeros)
    while cursor < len(blob) and blob[cursor] == 0:
        cursor += 1
    if cursor + 16 > len(blob):
        return None
    metadata = blob[cursor:cursor+16]
    size = struct.unpack_from("<I", metadata, 12)[0]
    data_start = cursor + 16
    return data_start, size, metadata, "v1"

def extract_all(binary_path, out_dir, source_version=None):
    blob, _, _, _ = find_bun_section(binary_path)
    os.makedirs(out_dir, exist_ok=True)
    
    manifest = []
    seen_paths = {} # path -> (data_start, size, metadata, version, prefix)
    
    for raw_path, path_start, path_end, prefix in iter_bun_paths(blob):
        entry = get_entry(blob, path_end)
        if not entry:
            continue
        data_start, size, metadata, version = entry
        
        if raw_path not in seen_paths:
            seen_paths[raw_path] = (data_start, size, metadata, version, prefix.decode())

    for raw_path, (data_start, size, metadata, version, prefix) in seen_paths.items():
        if raw_path.startswith("file:///"):
            rel_path = raw_path[len("file:///"):]
        elif raw_path.startswith("/$bunfs/root/"):
            rel_path = raw_path[len("/$bunfs/root/"):]
        else:
            rel_path = raw_path.lstrip("/")
            
        rel_path = rel_path.replace("..", "__")
        dest = Path(out_dir) / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob[data_start:data_start + size])
        
        manifest.append({
            "raw_path": raw_path,
            "rel_path": str(rel_path),
            "metadata_hex": metadata.hex(),
            "version": version,
            "prefix": prefix
        })
        
    with open(os.path.join(out_dir, ".bundle_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    write_source_metadata(out_dir, binary_path, source_version=source_version)
        
    print(f"[+] Extracted {len(manifest)} files to {out_dir}")
    return manifest

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: extractor.py <binary> <out_dir>")
    else:
        extract_all(sys.argv[1], sys.argv[2])
