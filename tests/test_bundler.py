import json
import pytest
from cc_extractor.bundler import pack_bundle
from cc_extractor.extractor import extract_all
from tests.helpers.bun_fixture import build_bun_fixture

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
