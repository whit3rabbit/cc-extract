import os
import json
import struct
from .macho import patch_macho
from .extractor import find_bun_section

def pack_bundle(indir, out_binary, base_binary):
    manifest_path = os.path.join(indir, ".bundle_manifest.json")
    if not os.path.exists(manifest_path):
        raise ValueError(f"No .bundle_manifest.json found in {indir}")
        
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
        
    bundle_blob = bytearray()
    
    print(f"[*] Packing {len(manifest)} files from {indir}...")
    for entry in manifest:
        rel_path = entry['rel_path']
        raw_path = entry['raw_path']
        metadata = bytes.fromhex(entry['metadata_hex'])
        
        file_path = os.path.join(indir, rel_path)
        if not os.path.exists(file_path):
             print(f"[!] Warning: missing file {file_path}, skipping")
             continue
             
        with open(file_path, "rb") as f:
            file_data = f.read()
        
        # Update size in metadata
        size = len(file_data)
        updated_metadata = bytearray(metadata)
        if entry['version'] == 'v2':
            struct.pack_into("<I", updated_metadata, 18, size)
        else:
            struct.pack_into("<I", updated_metadata, 12, size)
            
        path_bytes = raw_path.encode('utf-8')
        path_len = len(path_bytes)
        
        # Format: [path_len_le4][raw_path][metadata][data]
        bundle_blob.extend(struct.pack("<I", path_len))
        bundle_blob.extend(path_bytes)
        bundle_blob.extend(updated_metadata)
        bundle_blob.extend(file_data)
    
    # Inject into binary
    with open(base_binary, "rb") as f:
        binary_data = f.read()
    
    _, fileoff, old_size, _ = find_bun_section(base_binary)
    new_size = len(bundle_blob)
    
    # Create the new binary content
    if new_size <= old_size:
        print(f"[*] New bundle fits in old section (new: {new_size}, old: {old_size})")
        new_binary_data = bytearray(binary_data)
        new_binary_data[fileoff:fileoff + new_size] = bundle_blob
        # Zero out the rest of the old section to avoid confusion
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

    print(f"[+] Successfully bundled to {out_binary}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Usage: bundler.py <indir> <out_binary> <base_binary>")
    else:
        # Note: relative imports won't work if run directly, but this is for reference
        pack_bundle(sys.argv[1], sys.argv[2], sys.argv[3])
