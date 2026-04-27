import struct

LC_SEGMENT_64 = 0x19
MACHO_MAGIC_64 = 0xFEEDFACF

def patch_macho(binary_path, new_offset, new_size):
    with open(binary_path, 'rb+') as f:
        data = f.read(1024 * 1024) # Read first MB for header
        magic = struct.unpack_from("<I", data, 0)[0]
        if magic != MACHO_MAGIC_64:
            # Check for big-endian just in case, though unlikely for macOS x64/arm64
            raise ValueError("Only little-endian Mach-O 64-bit is supported for patching.")
        
        endian = "<"
        ncmds = struct.unpack_from(endian + "I", data, 16)[0]
        offset = 32
        
        found = False
        for _ in range(ncmds):
            cmd = struct.unpack_from(endian + "I", data, offset)[0]
            cmdsize = struct.unpack_from(endian + "I", data, offset + 4)[0]
            
            if cmd == LC_SEGMENT_64:
                segname = data[offset + 8: offset + 24].split(b"\x00", 1)[0].decode("utf-8", "ignore")
                if segname == "__BUN":
                    # Mach-O Segment structure indices (relative to offset):
                    # 0: cmd (4)
                    # 4: cmdsize (4)
                    # 8: segname (16)
                    # 24: vmaddr (8)
                    # 32: vmsize (8)
                    # 40: fileoff (8)
                    # 48: filesize (8)
                    # 64: nsects (4)
                    
                    # We'll align the size to 16KB (2^14)
                    aligned_size = (new_size + 0x3FFF) & (~0x3FFF)
                    
                    f.seek(offset + 32)
                    f.write(struct.pack(endian + "Q", aligned_size)) # vmsize
                    f.seek(offset + 48)
                    f.write(struct.pack(endian + "Q", new_size)) # filesize
                    
                    # Keep the segment file offset aligned with the rewritten __bun section.
                    f.seek(offset + 40)
                    f.write(struct.pack(endian + "Q", new_offset))
                    
                    # Now update sections
                    nsects = struct.unpack_from(endian + "I", data, offset + 64)[0]
                    sect_offset = offset + 72
                    for _ in range(nsects):
                        sectname_raw = data[sect_offset: sect_offset + 16]
                        sectname = sectname_raw.split(b"\x00", 1)[0].decode("utf-8", "ignore")
                        if sectname == "__bun":
                            # Section structure indices (relative to sect_offset):
                            # 0: sectname (16)
                            # 32: addr (8)
                            # 40: size (8)
                            # 48: offset (4)
                            f.seek(sect_offset + 40)
                            f.write(struct.pack(endian + "Q", new_size))
                            f.seek(sect_offset + 48)
                            f.write(struct.pack(endian + "I", new_offset))
                            found = True
                            break
                        sect_offset += 80
            
            if found: break
            offset += cmdsize
            
    if not found:
        raise ValueError("Could not find __BUN segment/section in Mach-O header.")
    print(f"[*] Patched Mach-O header: offset={new_offset}, size={new_size}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Usage: macho.py <binary> <new_offset> <new_size>")
    else:
        patch_macho(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
