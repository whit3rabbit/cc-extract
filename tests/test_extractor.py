import json
import hashlib
import struct

import pytest

from cc_extractor.extractor import (
    extract_all,
    find_bun_section,
    get_entry,
    iter_bun_paths,
    read_u32,
    read_u64,
)


def create_mock_macho(bun_offset, bun_size, is_big_endian=False):
    """Create a minimal valid Mach-O 64-bit binary with a __BUN section."""
    endian = '>' if is_big_endian else '<'

    magic = 0xCFFAEDFE if is_big_endian else 0xFEEDFACF
    header = bytearray(32)
    struct.pack_into(endian + "I", header, 0, magic)
    struct.pack_into(endian + "I", header, 4, 0x01000007)
    struct.pack_into(endian + "I", header, 8, 3)
    struct.pack_into(endian + "I", header, 12, 2)
    struct.pack_into(endian + "I", header, 16, 2)
    struct.pack_into(endian + "I", header, 20, 176)
    struct.pack_into(endian + "I", header, 24, 0)
    struct.pack_into(endian + "I", header, 28, 0)

    segment_cmd = bytearray(152)
    struct.pack_into(endian + "I", segment_cmd, 0, 0x19)
    struct.pack_into(endian + "I", segment_cmd, 4, 152)
    segment_cmd[8:24] = b'__BUN\x00\x00\x00\x00\x00\x00'
    struct.pack_into(endian + "Q", segment_cmd, 24, 0x1000)
    struct.pack_into(endian + "Q", segment_cmd, 32, bun_size)
    struct.pack_into(endian + "Q", segment_cmd, 40, bun_offset)
    struct.pack_into(endian + "Q", segment_cmd, 48, bun_size)
    struct.pack_into(endian + "I", segment_cmd, 64, 1)

    sect_offset = 72
    segment_cmd[sect_offset:sect_offset + 16] = b'__bun\x00\x00\x00\x00\x00'
    segment_cmd[sect_offset + 16:sect_offset + 32] = b'__BUN\x00\x00\x00\x00\x00\x00'
    struct.pack_into(endian + "Q", segment_cmd, sect_offset + 32, 0x1000)
    struct.pack_into(endian + "Q", segment_cmd, sect_offset + 40, bun_size)
    struct.pack_into(endian + "I", segment_cmd, sect_offset + 48, bun_offset)

    build_version = bytearray(24)
    struct.pack_into(endian + "I", build_version, 0, 0x8000001D)
    struct.pack_into(endian + "I", build_version, 4, 24)

    binary = bytearray(bun_offset + bun_size)
    binary[:len(header)] = header
    binary[len(header):len(header) + len(segment_cmd)] = segment_cmd
    binary[len(header) + len(segment_cmd):len(header) + len(segment_cmd) + len(build_version)] = build_version
    return bytes(binary)


def make_v2_entry(raw_path, file_data):
    path_bytes = raw_path.encode("utf-8")
    metadata = b"\xfa\xf9\x0d\x04" + (b"\x00" * 14) + struct.pack("<I", len(file_data))
    entry = struct.pack("<I", len(path_bytes)) + path_bytes + metadata + file_data
    return entry, metadata


class TestReadU32:
    def test_little_endian(self):
        data = b'\x04\x03\x02\x01'
        assert read_u32(data, 0, '<') == 0x01020304

    def test_big_endian(self):
        data = b'\x01\x02\x03\x04'
        assert read_u32(data, 0, '>') == 0x01020304


class TestReadU64:
    def test_little_endian(self):
        data = b'\x08\x07\x06\x05\x04\x03\x02\x01'
        assert read_u64(data, 0, '<') == 0x0102030405060708

    def test_big_endian(self):
        data = b'\x01\x02\x03\x04\x05\x06\x07\x08'
        assert read_u64(data, 0, '>') == 0x0102030405060708


class TestFindBunSection:
    def test_find_bun_section_little_endian(self, tmp_path):
        bun_data = b'\x00\x01\x02\x03\x04\x05\x06\x07' * 100
        bun_offset = 0x4000
        bun_size = len(bun_data)

        binary = bytearray(create_mock_macho(bun_offset, bun_size, is_big_endian=False))
        binary[bun_offset:bun_offset + bun_size] = bun_data

        binary_path = tmp_path / "claude"
        binary_path.write_bytes(binary)

        blob, fileoff, size, endian = find_bun_section(str(binary_path))

        assert blob == bun_data
        assert fileoff == bun_offset
        assert size == bun_size
        assert endian == "<"

    def test_binary_too_small(self, tmp_path):
        small_file = tmp_path / "small.bin"
        small_file.write_bytes(b'\x00' * 16)

        with pytest.raises(ValueError, match="Binary too small"):
            find_bun_section(str(small_file))

    def test_unsupported_format(self, tmp_path):
        invalid_file = tmp_path / "invalid.bin"
        invalid_file.write_bytes(b'\x11\x11\x11\x11' + b'\x00' * 64)

        with pytest.raises(ValueError, match="Unsupported binary format"):
            find_bun_section(str(invalid_file))


class TestIterBunPaths:
    def test_iter_bun_paths_file_url(self):
        raw_path = "file:///test.js"
        blob = struct.pack("<I", len(raw_path)) + raw_path.encode("utf-8")

        assert list(iter_bun_paths(blob)) == [
            (raw_path, 4, 4 + len(raw_path), b"file:///"),
        ]

    def test_iter_bun_paths_bunfs_root(self):
        raw_path = "/$bunfs/root/test.js"
        blob = struct.pack("<I", len(raw_path)) + raw_path.encode("utf-8")

        assert list(iter_bun_paths(blob)) == [
            (raw_path, 4, 4 + len(raw_path), b"/$bunfs/root/"),
        ]

    def test_iter_bun_paths_invalid_length(self):
        blob = b'\x00\x00\x00\x00file:///test.js'
        assert list(iter_bun_paths(blob)) == []

    def test_iter_bun_paths_length_too_large(self):
        blob = b'\xff\xff\x00\x00file:///test.js'
        assert list(iter_bun_paths(blob)) == []

    def test_iter_bun_paths_no_match(self):
        blob = b'some random data without paths'
        assert list(iter_bun_paths(blob)) == []


class TestGetEntry:
    def test_get_entry_v2_signature(self):
        metadata = b"\xfa\xf9\x0d\x04" + (b"\x00" * 14) + struct.pack("<I", 8)
        payload = b"contents"
        blob = b'\x00' * 10 + metadata + payload

        result = get_entry(blob, 10)

        assert result == (32, 8, metadata, "v2")

    def test_get_entry_v1(self):
        metadata = b'\xaa' * 12 + struct.pack("<I", 8)
        payload = b"contents"
        blob = b'\x00' * 10 + b'\x00' * 3 + metadata + payload

        result = get_entry(blob, 10)

        assert result == (29, 8, metadata, "v1")

    def test_get_entry_at_end(self):
        blob = b'\x00' * 10
        assert get_entry(blob, 0) is None


class TestExtractAll:
    def test_extract_all_creates_manifest(self, tmp_path):
        bun_offset = 0x4000
        file_data = b'console.log();'
        raw_path = "file:///test.js"
        entry, metadata = make_v2_entry(raw_path, file_data)
        bun_size = len(entry) + 32

        binary = bytearray(create_mock_macho(bun_offset, bun_size))
        binary[bun_offset:bun_offset + len(entry)] = entry

        binary_path = tmp_path / 'claude'
        binary_path.write_bytes(binary)

        out_dir = tmp_path / 'output'
        manifest = extract_all(str(binary_path), str(out_dir))

        manifest_path = out_dir / '.bundle_manifest.json'
        source_metadata_path = out_dir / '.bundle_source.json'
        extracted_file = out_dir / 'test.js'

        assert manifest_path.exists()
        assert source_metadata_path.exists()
        assert extracted_file.read_bytes() == file_data
        assert manifest == [
            {
                "raw_path": raw_path,
                "rel_path": "test.js",
                "metadata_hex": metadata.hex(),
                "version": "v2",
                "prefix": "file:///",
            }
        ]
        assert json.loads(manifest_path.read_text()) == manifest
        assert json.loads(source_metadata_path.read_text()) == {
            "binary_sha256": hashlib.sha256(binary_path.read_bytes()).hexdigest(),
        }

    def test_extract_all_writes_source_version_metadata(self, tmp_path):
        bun_offset = 0x4000
        file_data = b'console.log();'
        raw_path = "file:///test.js"
        entry, _ = make_v2_entry(raw_path, file_data)
        bun_size = len(entry) + 32

        binary = bytearray(create_mock_macho(bun_offset, bun_size))
        binary[bun_offset:bun_offset + len(entry)] = entry

        binary_path = tmp_path / 'claude'
        binary_path.write_bytes(binary)

        out_dir = tmp_path / 'output'
        extract_all(str(binary_path), str(out_dir), source_version="1.2.3")

        assert json.loads((out_dir / '.bundle_source.json').read_text()) == {
            "binary_sha256": hashlib.sha256(binary_path.read_bytes()).hexdigest(),
            "source_version": "1.2.3",
        }
