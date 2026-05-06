import json
import struct
import pytest
from ccsilo.bundler import pack_bundle
from ccsilo.bun_extract import parse_bun_binary
from ccsilo.bun_extract.constants import OFFSETS_SIZE, TRAILER
from ccsilo.extractor import extract_all
from tests.helpers.bun_fixture import build_bun_fixture

def write_manifest(indir, manifest):
    (indir / '.bundle_manifest.json').write_text(json.dumps(manifest))


def build_elf_with_unreferenced_prefix():
    raw_name = b"/$bunfs/root/src/index.js"
    content = b"console.log(0);"
    prefix = b"KEEP"
    module_size = 52
    name_off = len(prefix)
    content_off = name_off + len(raw_name)
    modules_off = content_off + len(content)
    raw = bytearray(prefix + raw_name + content + (b"\x00" * module_size))
    struct.pack_into("<IIIIIIII", raw, modules_off, name_off, len(raw_name), content_off, len(content), 0, 0, 0, 0)
    raw[modules_off + 48 : modules_off + 52] = b"\x02\x01\x01\x00"

    offsets = bytearray(OFFSETS_SIZE)
    struct.pack_into("<Q", offsets, 0, len(raw))
    struct.pack_into("<I", offsets, 8, modules_off)
    struct.pack_into("<I", offsets, 12, module_size)
    struct.pack_into("<I", offsets, 20, len(raw) - 1)

    header = bytearray(64)
    header[:4] = b"\x7fELF"
    return bytes(header) + bytes(raw) + bytes(offsets) + TRAILER

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

    def test_pack_bundle_preserves_extracted_elf_payload_template(self, tmp_path):
        base = build_elf_with_unreferenced_prefix()
        base_binary = tmp_path / "base"
        base_binary.write_bytes(base)
        extract_dir = tmp_path / "extract"
        extract_all(str(base_binary), str(extract_dir))

        out_binary = tmp_path / "output"
        pack_bundle(str(extract_dir), str(out_binary), str(base_binary))

        assert out_binary.read_bytes() == base

    def test_pack_bundle_resizes_elf_source_without_dropping_raw_names_or_prefix(self, tmp_path):
        base = build_elf_with_unreferenced_prefix()
        base_binary = tmp_path / "base"
        base_binary.write_bytes(base)
        extract_dir = tmp_path / "extract"
        extract_all(str(base_binary), str(extract_dir))
        (extract_dir / "src" / "index.js").write_bytes(b"console.log(123456);")

        out_binary = tmp_path / "output"
        pack_bundle(str(extract_dir), str(out_binary), str(base_binary))

        out = out_binary.read_bytes()
        info = parse_bun_binary(out)
        module = info.modules[0]
        assert out[info.data_start : info.data_start + 4] == b"KEEP"
        assert module.name == "src/index.js"
        assert module.raw_name == "/$bunfs/root/src/index.js"
        assert out[info.data_start + module.cont_off : info.data_start + module.cont_off + module.cont_len] == (
            b"console.log(123456);"
        )

    def test_pack_bundle_rejects_manifest_path_traversal(self, tmp_path):
        indir = tmp_path / 'input'
        indir.mkdir()
        outside = tmp_path / 'secret.txt'
        outside.write_text('do not bundle me', encoding='utf-8')

        manifest = {
            "isMacho": True,
            "entryPointId": 0,
            "flags": 0,
            "modules": [
                {
                    "name": "src/index.js",
                    "rel_path": "src/index.js",
                    "sourceFile": "../secret.txt",
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
            modules=[{"name": "src/index.js", "content": "console.log(0);"}],
        )
        base_binary.write_bytes(base_fixture["buf"])

        with pytest.raises(ValueError, match="modules\\[0\\].sourceFile"):
            pack_bundle(str(indir), str(tmp_path / 'output'), str(base_binary))

    def test_pack_bundle_rejects_windows_drive_manifest_path(self, tmp_path):
        indir = tmp_path / 'input'
        indir.mkdir()
        manifest = {
            "isMacho": True,
            "entryPointId": 0,
            "flags": 0,
            "modules": [
                {
                    "name": "src/index.js",
                    "rel_path": "src/index.js",
                    "sourceFile": "C:/Users/alice/secret.txt",
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
            modules=[{"name": "src/index.js", "content": "console.log(0);"}],
        )
        base_binary.write_bytes(base_fixture["buf"])

        with pytest.raises(ValueError, match="modules\\[0\\].sourceFile"):
            pack_bundle(str(indir), str(tmp_path / 'output'), str(base_binary))

    def test_pack_bundle_rejects_manifest_symlink_escape(self, tmp_path):
        indir = tmp_path / 'input'
        indir.mkdir()
        outside = tmp_path / 'secret.txt'
        outside.write_text('do not bundle me', encoding='utf-8')
        (indir / 'src').mkdir()
        try:
            (indir / 'src' / 'link.js').symlink_to(outside)
        except OSError as exc:
            pytest.skip(f"symlink unavailable: {exc}")

        manifest = {
            "isMacho": True,
            "entryPointId": 0,
            "flags": 0,
            "modules": [
                {
                    "name": "src/index.js",
                    "rel_path": "src/index.js",
                    "sourceFile": "src/link.js",
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
            modules=[{"name": "src/index.js", "content": "console.log(0);"}],
        )
        base_binary.write_bytes(base_fixture["buf"])

        with pytest.raises(ValueError, match="escapes root"):
            pack_bundle(str(indir), str(tmp_path / 'output'), str(base_binary))
