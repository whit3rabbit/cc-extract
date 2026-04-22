import json
import struct

import pytest

from cc_extractor.bundler import pack_bundle
from cc_extractor.macho import LC_SEGMENT_64, MACHO_MAGIC_64, patch_macho


def create_test_macho(bun_offset, bun_size):
    """Create a minimal Mach-O 64-bit binary for testing."""
    header = bytearray(32)
    struct.pack_into("<I", header, 0, MACHO_MAGIC_64)
    struct.pack_into("<I", header, 16, 1)

    segment = bytearray(152)
    struct.pack_into("<I", segment, 0, LC_SEGMENT_64)
    struct.pack_into("<I", segment, 4, 152)
    segment[8:24] = b'__BUN\x00\x00\x00\x00\x00\x00'
    struct.pack_into("<Q", segment, 32, bun_size)
    struct.pack_into("<Q", segment, 40, bun_offset)
    struct.pack_into("<Q", segment, 48, bun_size)
    struct.pack_into("<I", segment, 64, 1)

    sect_offset = 72
    segment[sect_offset:sect_offset + 16] = b'__bun\x00\x00\x00\x00\x00'
    segment[sect_offset + 16:sect_offset + 32] = b'__BUN\x00\x00\x00\x00\x00\x00'
    struct.pack_into("<Q", segment, sect_offset + 40, bun_size)
    struct.pack_into("<I", segment, sect_offset + 48, bun_offset)

    binary = bytearray(bun_offset + bun_size)
    binary[:len(header)] = header
    binary[len(header):len(header) + len(segment)] = segment
    return bytes(binary)


def make_v2_metadata():
    return b"\xfa\xf9\x0d\x04" + (b"\x00" * 14) + struct.pack("<I", 0)


def read_bun_headers(binary_path):
    data = binary_path.read_bytes()
    offset = 32
    sect_offset = offset + 72

    return {
        "data": data,
        "segment_vmsize": struct.unpack_from("<Q", data, offset + 32)[0],
        "segment_fileoff": struct.unpack_from("<Q", data, offset + 40)[0],
        "segment_filesize": struct.unpack_from("<Q", data, offset + 48)[0],
        "section_size": struct.unpack_from("<Q", data, sect_offset + 40)[0],
        "section_offset": struct.unpack_from("<I", data, sect_offset + 48)[0],
    }


def build_expected_bundle(indir, manifest):
    bundle = bytearray()

    for entry in manifest:
        file_path = indir / entry["rel_path"]
        if not file_path.exists():
            continue

        file_data = file_path.read_bytes()
        metadata = bytearray(bytes.fromhex(entry["metadata_hex"]))
        if entry["version"] == "v2":
            struct.pack_into("<I", metadata, 18, len(file_data))
        else:
            struct.pack_into("<I", metadata, 12, len(file_data))

        path_bytes = entry["raw_path"].encode("utf-8")
        bundle.extend(struct.pack("<I", len(path_bytes)))
        bundle.extend(path_bytes)
        bundle.extend(metadata)
        bundle.extend(file_data)

    return bytes(bundle)


def write_manifest(indir, manifest):
    (indir / '.bundle_manifest.json').write_text(json.dumps(manifest))


class TestPackBundle:
    def test_pack_bundle_missing_manifest(self, tmp_path):
        indir = tmp_path / 'input'
        indir.mkdir()
        out_binary = tmp_path / 'output'
        base_binary = tmp_path / 'base'

        with pytest.raises(ValueError, match="No .bundle_manifest.json"):
            pack_bundle(str(indir), str(out_binary), str(base_binary))

    def test_pack_bundle_missing_file(self, tmp_path):
        indir = tmp_path / 'input'
        indir.mkdir()

        manifest = [
            {
                "rel_path": "nonexistent.js",
                "raw_path": "file:///nonexistent.js",
                "metadata_hex": make_v2_metadata().hex(),
                "version": "v2",
            }
        ]
        write_manifest(indir, manifest)

        bun_offset = 0x4000
        bun_size = 0x1000
        base_binary = tmp_path / 'base'
        base_binary.write_bytes(create_test_macho(bun_offset, bun_size))

        out_binary = tmp_path / 'output'
        pack_bundle(str(indir), str(out_binary), str(base_binary))

        headers = read_bun_headers(out_binary)
        assert out_binary.exists()
        assert headers["segment_fileoff"] == bun_offset
        assert headers["segment_filesize"] == 0
        assert headers["section_size"] == 0

    def test_pack_bundle_reuses_existing_bun_section_when_bundle_fits(self, tmp_path):
        indir = tmp_path / 'input'
        indir.mkdir()
        rel_path = 'test.js'
        file_data = b'console.log(1);'
        (indir / rel_path).write_bytes(file_data)

        manifest = [
            {
                "rel_path": rel_path,
                "raw_path": "file:///test.js",
                "metadata_hex": make_v2_metadata().hex(),
                "version": "v2",
            }
        ]
        write_manifest(indir, manifest)
        expected_bundle = build_expected_bundle(indir, manifest)

        bun_offset = 0x4000
        bun_size = len(expected_bundle) + 128
        base_binary = tmp_path / 'base'
        base_binary.write_bytes(create_test_macho(bun_offset, bun_size))

        out_binary = tmp_path / 'output'
        pack_bundle(str(indir), str(out_binary), str(base_binary))

        headers = read_bun_headers(out_binary)
        assert len(headers["data"]) == len(base_binary.read_bytes())
        assert headers["segment_fileoff"] == bun_offset
        assert headers["segment_filesize"] == len(expected_bundle)
        assert headers["section_size"] == len(expected_bundle)
        assert headers["section_offset"] == bun_offset
        assert headers["data"][bun_offset:bun_offset + len(expected_bundle)] == expected_bundle
        assert headers["data"][bun_offset + len(expected_bundle):bun_offset + bun_size] == (
            b"\x00" * (bun_size - len(expected_bundle))
        )

    def test_pack_bundle_appends_bundle_when_it_grows(self, tmp_path):
        indir = tmp_path / 'input'
        indir.mkdir()
        rel_path = 'nested/test.js'
        (indir / 'nested').mkdir()
        file_data = b'x' * 128
        (indir / rel_path).write_bytes(file_data)

        manifest = [
            {
                "rel_path": rel_path,
                "raw_path": "file:///nested/test.js",
                "metadata_hex": make_v2_metadata().hex(),
                "version": "v2",
            }
        ]
        write_manifest(indir, manifest)
        expected_bundle = build_expected_bundle(indir, manifest)

        bun_offset = 0x4000
        bun_size = 32
        base_binary = tmp_path / 'base'
        base_binary.write_bytes(create_test_macho(bun_offset, bun_size))
        base_data = base_binary.read_bytes()

        out_binary = tmp_path / 'output'
        pack_bundle(str(indir), str(out_binary), str(base_binary))

        headers = read_bun_headers(out_binary)
        appended_offset = len(base_data)
        assert len(headers["data"]) == len(base_data) + len(expected_bundle)
        assert headers["segment_fileoff"] == appended_offset
        assert headers["segment_filesize"] == len(expected_bundle)
        assert headers["section_size"] == len(expected_bundle)
        assert headers["section_offset"] == appended_offset
        assert headers["data"][appended_offset:] == expected_bundle


class TestPatchMacho:
    def test_patch_macho_updates_headers(self, tmp_path):
        bun_offset = 0x4000
        bun_size = 0x1000

        binary_path = tmp_path / 'test'
        binary_path.write_bytes(create_test_macho(bun_offset, bun_size))

        new_offset = 0x5000
        new_size = 0x800

        patch_macho(str(binary_path), new_offset, new_size)
        headers = read_bun_headers(binary_path)

        assert headers["segment_fileoff"] == new_offset
        assert headers["segment_filesize"] == new_size
        assert headers["segment_vmsize"] == 0x4000
        assert headers["section_size"] == new_size
        assert headers["section_offset"] == new_offset

    def test_patch_macho_invalid_magic(self, tmp_path):
        binary_path = tmp_path / 'test'
        binary_path.write_bytes(b'\x00\x00\x00\x00' + b'\x00' * 100)

        with pytest.raises(ValueError, match="little-endian Mach-O 64-bit"):
            patch_macho(str(binary_path), 0x1000, 0x1000)

    def test_patch_macho_no_bun_segment(self, tmp_path):
        binary_path = tmp_path / 'test'

        header = bytearray(32)
        struct.pack_into("<I", header, 0, MACHO_MAGIC_64)
        struct.pack_into("<I", header, 16, 1)

        segment = bytearray(72)
        struct.pack_into("<I", segment, 0, LC_SEGMENT_64)
        segment[8:24] = b'__TEXT\x00\x00\x00\x00\x00\x00'

        binary_path.write_bytes(bytes(header) + bytes(segment))

        with pytest.raises(ValueError, match="Could not find __BUN"):
            patch_macho(str(binary_path), 0x1000, 0x1000)
