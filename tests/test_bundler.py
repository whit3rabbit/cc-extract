import json
import struct
import pytest
from cc_extractor.bundler import pack_bundle
from cc_extractor.extractor import extract_all
from cc_extractor.macho import LC_SEGMENT_64, MACHO_MAGIC_64, patch_macho
from tests.helpers.bun_fixture import build_bun_fixture

def create_test_macho(bun_offset, bun_size):
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

    def test_pack_bundle_creates_macho(self, tmp_path):
        indir = tmp_path / 'input'
        indir.mkdir()
        rel_path = 'src/index.js'
        (indir / 'src').mkdir()
        file_data = b'console.log(1);'
        (indir / rel_path).write_bytes(file_data)

        manifest = {
            "isMacho": True,
            "entryPointId": 0,
            "flags": 0,
            "modules": [
                {
                    "name": rel_path,
                    "rel_path": rel_path,
                    "sourceFile": rel_path,
                    "encoding": 2,
                    "loader": 1,
                    "format": 1,
                    "side": 0
                }
            ]
        }
        write_manifest(indir, manifest)

        base_binary = tmp_path / 'base'
        base_fixture = build_bun_fixture(
            platform="macho",
            module_struct_size=52,
            modules=[{"name": rel_path, "content": "console.log(0);"}],
        )
        base_binary.write_bytes(base_fixture["buf"])

        out_binary = tmp_path / 'output'
        pack_bundle(str(indir), str(out_binary), str(base_binary))

        assert out_binary.exists()
        out_data = out_binary.read_bytes()
        assert b"\n---- Bun! ----\n" in out_data

        roundtrip_dir = tmp_path / "roundtrip"
        manifest = extract_all(str(out_binary), str(roundtrip_dir))
        assert manifest["platform"] == "macho"
        assert (roundtrip_dir / rel_path).read_bytes() == file_data

class TestPatchMacho:
    def test_patch_macho_updates_headers(self, tmp_path):
        bun_offset = 0x4000
        bun_size = 0x1000
        binary_path = tmp_path / 'test'
        binary_path.write_bytes(create_test_macho(bun_offset, bun_size))

        new_offset = 0x5000
        new_size = 0x800
        patch_macho(str(binary_path), new_offset, new_size)
