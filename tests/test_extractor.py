import json
import hashlib
import struct
import pytest
from cc_extractor.extractor import extract_all, read_u32, read_u64

def create_mock_macho(bun_offset, bun_size):
    """Create a minimal valid Mach-O 64-bit binary with a __BUN section."""
    endian = '<'
    header = bytearray(32)
    struct.pack_into(endian + "I", header, 0, 0xFEEDFACF)
    struct.pack_into(endian + "I", header, 16, 1)

    segment_cmd = bytearray(152)
    struct.pack_into(endian + "I", segment_cmd, 0, 0x19)
    struct.pack_into(endian + "I", segment_cmd, 4, 152)
    segment_cmd[8:24] = b'__BUN\x00\x00\x00\x00\x00\x00'
    struct.pack_into(endian + "Q", segment_cmd, 32, bun_size)
    struct.pack_into(endian + "Q", segment_cmd, 40, bun_offset)
    struct.pack_into(endian + "Q", segment_cmd, 48, bun_size)
    struct.pack_into(endian + "I", segment_cmd, 64, 1)

    sect_offset = 72
    segment_cmd[sect_offset:sect_offset + 16] = b'__bun\x00\x00\x00\x00\x00'
    segment_cmd[sect_offset + 16:sect_offset + 32] = b'__BUN\x00\x00\x00\x00\x00\x00'
    struct.pack_into(endian + "Q", segment_cmd, sect_offset + 40, bun_size)
    struct.pack_into(endian + "I", segment_cmd, sect_offset + 48, bun_offset)

    binary = bytearray(bun_offset + bun_size)
    binary[:len(header)] = header
    binary[len(header):len(header) + len(segment_cmd)] = segment_cmd
    return bytes(binary)

def create_mock_standalone_graph():
    name = b"src/index.js"
    source = b"console.log('hello');"
    data_buffer = bytearray()
    
    name_off = len(data_buffer)
    data_buffer.extend(name)
    name_len = len(name)
    
    cont_off = len(data_buffer)
    data_buffer.extend(source)
    cont_len = len(source)
    
    smap_off, smap_len = 0, 0
    bc_off, bc_len = 0, 0
    mod_offset = len(data_buffer)
    
    struct_data = struct.pack("<IIIIIIII", name_off, name_len, cont_off, cont_len, smap_off, smap_len, bc_off, bc_len)
    struct_data += bytes(16)
    struct_data += struct.pack("BBBB", 2, 1, 1, 0)
    
    module_table = struct_data
    mod_length = len(module_table)
    byte_count = mod_offset + mod_length
    
    offsets_struct = struct.pack("<QIIIIII", byte_count, mod_offset, mod_length, 0, 0, 0, 0)
    trailer = b"\n---- Bun! ----\n"
    
    return data_buffer + module_table + offsets_struct + trailer

class TestReadU32:
    def test_little_endian(self):
        data = b'\x04\x03\x02\x01'
        assert read_u32(data, 0, '<') == 0x01020304

class TestReadU64:
    def test_little_endian(self):
        data = b'\x08\x07\x06\x05\x04\x03\x02\x01'
        assert read_u64(data, 0, '<') == 0x0102030405060708

class TestExtractAll:
    def test_extract_all_creates_manifest(self, tmp_path):
        payload = create_mock_standalone_graph()
        bun_offset = 0x4000
        bun_size = len(payload) + 8
        
        binary = bytearray(create_mock_macho(bun_offset, bun_size))
        # Add 8-byte size header
        struct.pack_into("<Q", binary, bun_offset, bun_size)
        binary[bun_offset + 8 : bun_offset + 8 + len(payload)] = payload

        binary_path = tmp_path / 'claude'
        binary_path.write_bytes(binary)

        out_dir = tmp_path / 'output'
        manifest = extract_all(str(binary_path), str(out_dir))

        manifest_path = out_dir / '.bundle_manifest.json'
        source_metadata_path = out_dir / '.bundle_source.json'
        extracted_file = out_dir / 'src/index.js'

        assert manifest_path.exists()
        assert source_metadata_path.exists()
        assert extracted_file.read_bytes() == b"console.log('hello');"
        assert len(manifest["modules"]) == 1
        assert manifest["modules"][0]["rel_path"] == "src/index.js"
