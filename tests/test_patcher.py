import hashlib
import json
import struct

import pytest

from cc_extractor.bundler import pack_bundle
from cc_extractor.extractor import extract_all
from cc_extractor.patcher import apply_patch, init_patch, write_source_metadata


def create_mock_macho(bun_offset, bun_size):
    header = bytearray(32)
    struct.pack_into("<I", header, 0, 0xFEEDFACF)
    struct.pack_into("<I", header, 4, 0x01000007)
    struct.pack_into("<I", header, 8, 3)
    struct.pack_into("<I", header, 12, 2)
    struct.pack_into("<I", header, 16, 2)
    struct.pack_into("<I", header, 20, 176)
    struct.pack_into("<I", header, 24, 0)
    struct.pack_into("<I", header, 28, 0)

    segment_cmd = bytearray(152)
    struct.pack_into("<I", segment_cmd, 0, 0x19)
    struct.pack_into("<I", segment_cmd, 4, 152)
    segment_cmd[8:24] = b'__BUN\x00\x00\x00\x00\x00\x00'
    struct.pack_into("<Q", segment_cmd, 24, 0x1000)
    struct.pack_into("<Q", segment_cmd, 32, bun_size)
    struct.pack_into("<Q", segment_cmd, 40, bun_offset)
    struct.pack_into("<Q", segment_cmd, 48, bun_size)
    struct.pack_into("<I", segment_cmd, 64, 1)

    sect_offset = 72
    segment_cmd[sect_offset:sect_offset + 16] = b'__bun\x00\x00\x00\x00\x00'
    segment_cmd[sect_offset + 16:sect_offset + 32] = b'__BUN\x00\x00\x00\x00\x00\x00'
    struct.pack_into("<Q", segment_cmd, sect_offset + 32, 0x1000)
    struct.pack_into("<Q", segment_cmd, sect_offset + 40, bun_size)
    struct.pack_into("<I", segment_cmd, sect_offset + 48, bun_offset)

    build_version = bytearray(24)
    struct.pack_into("<I", build_version, 0, 0x8000001D)
    struct.pack_into("<I", build_version, 4, 24)

    binary = bytearray(bun_offset + bun_size)
    binary[:len(header)] = header
    binary[len(header):len(header) + len(segment_cmd)] = segment_cmd
    binary[len(header) + len(segment_cmd):len(header) + len(segment_cmd) + len(build_version)] = build_version
    return bytes(binary)


def make_v2_entry(raw_path, file_data):
    path_bytes = raw_path.encode("utf-8")
    metadata = b"\xfa\xf9\x0d\x04" + (b"\x00" * 14) + struct.pack("<I", len(file_data))
    entry = struct.pack("<I", len(path_bytes)) + path_bytes + metadata + file_data
    return entry


def make_extract_dir(tmp_path, content="const value = 'before';\n", write_metadata=False, source_version="1.2.3"):
    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()
    target_path = extract_dir / "app.js"
    target_path.write_text(content, encoding="utf-8")

    binary_path = tmp_path / "claude"
    binary_path.write_bytes(b"binary-data")

    if write_metadata:
        write_source_metadata(extract_dir, binary_path, source_version=source_version)

    return extract_dir, target_path, binary_path


def write_patch_manifest(patch_dir, manifest):
    patch_dir.mkdir(parents=True, exist_ok=True)
    (patch_dir / "patch.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def make_patch_manifest(*, targets=None, operations=None):
    if operations is None:
        operations = [
            {
                "type": "replace_string",
                "path": "app.js",
                "find": "before",
                "replace": "after",
            }
        ]

    return {
        "id": "test.patch",
        "description": "Test patch",
        "targets": targets or {
            "versions": [],
            "binary_sha256": [],
        },
        "operations": operations,
    }


class TestInitPatch:
    def test_init_patch_creates_scaffold(self, tmp_path):
        patch_dir = tmp_path / "patch"

        init_patch(patch_dir)

        manifest = json.loads((patch_dir / "patch.json").read_text())
        assert manifest["id"] == "example.patch"
        assert manifest["targets"] == {
            "versions": [],
            "binary_sha256": [],
        }
        assert [op["type"] for op in manifest["operations"]] == [
            "replace_string",
            "replace_block",
        ]
        assert (patch_dir / "blocks" / "find_example.js").exists()
        assert (patch_dir / "blocks" / "replace_example.js").exists()


class TestPatchTargets:
    def test_apply_patch_accepts_matching_version_and_checksum(self, tmp_path):
        extract_dir, target_path, binary_path = make_extract_dir(tmp_path, write_metadata=True)
        checksum = hashlib.sha256(binary_path.read_bytes()).hexdigest()

        patch_dir = tmp_path / "patch"
        write_patch_manifest(
            patch_dir,
            make_patch_manifest(
                targets={
                    "versions": ["1.2.3"],
                    "binary_sha256": [checksum],
                },
            ),
        )

        apply_patch(patch_dir, extract_dir)

        assert target_path.read_text(encoding="utf-8") == "const value = 'after';\n"

    def test_apply_patch_rejects_version_mismatch(self, tmp_path):
        extract_dir, _, binary_path = make_extract_dir(tmp_path, write_metadata=True, source_version="1.2.3")
        checksum = hashlib.sha256(binary_path.read_bytes()).hexdigest()

        patch_dir = tmp_path / "patch"
        write_patch_manifest(
            patch_dir,
            make_patch_manifest(
                targets={
                    "versions": ["9.9.9"],
                    "binary_sha256": [checksum],
                },
            ),
        )

        with pytest.raises(ValueError, match="source version"):
            apply_patch(patch_dir, extract_dir)

    def test_apply_patch_rejects_checksum_mismatch(self, tmp_path):
        extract_dir, _, _ = make_extract_dir(tmp_path, write_metadata=True)
        other_binary = tmp_path / "other-claude"
        other_binary.write_bytes(b"other-binary-data")
        checksum = hashlib.sha256(other_binary.read_bytes()).hexdigest()

        patch_dir = tmp_path / "patch"
        write_patch_manifest(
            patch_dir,
            make_patch_manifest(
                targets={
                    "versions": [],
                    "binary_sha256": [checksum],
                },
            ),
        )

        with pytest.raises(ValueError, match="checksum"):
            apply_patch(patch_dir, extract_dir)

    def test_apply_patch_requires_metadata_or_overrides_for_targeted_patch(self, tmp_path):
        extract_dir, _, binary_path = make_extract_dir(tmp_path, write_metadata=False)
        checksum = hashlib.sha256(binary_path.read_bytes()).hexdigest()

        patch_dir = tmp_path / "patch"
        write_patch_manifest(
            patch_dir,
            make_patch_manifest(
                targets={
                    "versions": ["1.2.3"],
                    "binary_sha256": [checksum],
                },
            ),
        )

        with pytest.raises(ValueError, match="source version metadata"):
            apply_patch(patch_dir, extract_dir)

    def test_apply_patch_accepts_overrides_when_source_metadata_is_missing(self, tmp_path):
        extract_dir, target_path, binary_path = make_extract_dir(tmp_path, write_metadata=False)
        checksum = hashlib.sha256(binary_path.read_bytes()).hexdigest()

        patch_dir = tmp_path / "patch"
        write_patch_manifest(
            patch_dir,
            make_patch_manifest(
                targets={
                    "versions": ["1.2.3"],
                    "binary_sha256": [checksum],
                },
            ),
        )

        apply_patch(
            patch_dir,
            extract_dir,
            binary_path=binary_path,
            source_version="1.2.3",
        )

        assert target_path.read_text(encoding="utf-8") == "const value = 'after';\n"


class TestReplaceString:
    def test_replace_string_exact_single_match_success(self, tmp_path):
        extract_dir, target_path, _ = make_extract_dir(tmp_path, content="one before two\n")

        patch_dir = tmp_path / "patch"
        write_patch_manifest(patch_dir, make_patch_manifest())

        apply_patch(patch_dir, extract_dir)

        assert target_path.read_text(encoding="utf-8") == "one after two\n"

    def test_replace_string_zero_matches(self, tmp_path):
        extract_dir, _, _ = make_extract_dir(tmp_path, content="no target here\n")

        patch_dir = tmp_path / "patch"
        write_patch_manifest(patch_dir, make_patch_manifest())

        with pytest.raises(ValueError, match="found no matches"):
            apply_patch(patch_dir, extract_dir)

    def test_replace_string_rejects_multiple_matches_when_count_is_default(self, tmp_path):
        extract_dir, _, _ = make_extract_dir(tmp_path, content="before and before\n")

        patch_dir = tmp_path / "patch"
        write_patch_manifest(patch_dir, make_patch_manifest())

        with pytest.raises(ValueError, match="expected 1 match"):
            apply_patch(patch_dir, extract_dir)

    def test_replace_string_allows_multiple_matches_when_count_matches(self, tmp_path):
        extract_dir, target_path, _ = make_extract_dir(tmp_path, content="before and before\n")

        patch_dir = tmp_path / "patch"
        write_patch_manifest(
            patch_dir,
            make_patch_manifest(
                operations=[
                    {
                        "type": "replace_string",
                        "path": "app.js",
                        "find": "before",
                        "replace": "after",
                        "count": 2,
                    }
                ],
            ),
        )

        apply_patch(patch_dir, extract_dir)

        assert target_path.read_text(encoding="utf-8") == "after and after\n"


class TestReplaceBlock:
    def test_replace_block_success(self, tmp_path):
        extract_dir, target_path, _ = make_extract_dir(
            tmp_path,
            content="function example() {\n  return 'before';\n}\n",
        )

        patch_dir = tmp_path / "patch"
        (patch_dir / "blocks").mkdir(parents=True)
        (patch_dir / "blocks" / "find.js").write_text(
            "function example() {\n  return 'before';\n}\n",
            encoding="utf-8",
        )
        (patch_dir / "blocks" / "replace.js").write_text(
            "function example() {\n  return 'after';\n}\n",
            encoding="utf-8",
        )
        write_patch_manifest(
            patch_dir,
            make_patch_manifest(
                operations=[
                    {
                        "type": "replace_block",
                        "path": "app.js",
                        "find_file": "blocks/find.js",
                        "replace_file": "blocks/replace.js",
                    }
                ],
            ),
        )

        apply_patch(patch_dir, extract_dir)

        assert target_path.read_text(encoding="utf-8") == "function example() {\n  return 'after';\n}\n"

    def test_replace_block_missing_asset(self, tmp_path):
        extract_dir, _, _ = make_extract_dir(
            tmp_path,
            content="function example() {\n  return 'before';\n}\n",
        )

        patch_dir = tmp_path / "patch"
        write_patch_manifest(
            patch_dir,
            make_patch_manifest(
                operations=[
                    {
                        "type": "replace_block",
                        "path": "app.js",
                        "find_file": "blocks/find.js",
                        "replace_file": "blocks/replace.js",
                    }
                ],
            ),
        )

        with pytest.raises(ValueError, match="Patch asset does not exist"):
            apply_patch(patch_dir, extract_dir)

    def test_replace_block_count_mismatch(self, tmp_path):
        extract_dir, _, _ = make_extract_dir(
            tmp_path,
            content=(
                "function example() {\n  return 'before';\n}\n"
                "function example() {\n  return 'before';\n}\n"
            ),
        )

        patch_dir = tmp_path / "patch"
        (patch_dir / "blocks").mkdir(parents=True)
        (patch_dir / "blocks" / "find.js").write_text(
            "function example() {\n  return 'before';\n}\n",
            encoding="utf-8",
        )
        (patch_dir / "blocks" / "replace.js").write_text(
            "function example() {\n  return 'after';\n}\n",
            encoding="utf-8",
        )
        write_patch_manifest(
            patch_dir,
            make_patch_manifest(
                operations=[
                    {
                        "type": "replace_block",
                        "path": "app.js",
                        "find_file": "blocks/find.js",
                        "replace_file": "blocks/replace.js",
                    }
                ],
            ),
        )

        with pytest.raises(ValueError, match="expected 1 match"):
            apply_patch(patch_dir, extract_dir)


class TestPatchCheckMode:
    def test_check_mode_does_not_mutate_files(self, tmp_path):
        extract_dir, target_path, _ = make_extract_dir(tmp_path, content="before only\n")

        patch_dir = tmp_path / "patch"
        write_patch_manifest(
            patch_dir,
            make_patch_manifest(
                operations=[
                    {
                        "type": "replace_string",
                        "path": "app.js",
                        "find": "before",
                        "replace": "after",
                    }
                ],
            ),
        )

        apply_patch(patch_dir, extract_dir, check=True)

        assert target_path.read_text(encoding="utf-8") == "before only\n"


class TestEndToEndPatchFlow:
    def test_extract_apply_patch_and_pack_round_trip(self, tmp_path):
        bun_offset = 0x4000
        original_data = b"console.log('before');\n"
        raw_path = "file:///app.js"
        entry = make_v2_entry(raw_path, original_data)
        bun_size = len(entry) + 32

        base_binary = tmp_path / "claude"
        binary = bytearray(create_mock_macho(bun_offset, bun_size))
        binary[bun_offset:bun_offset + len(entry)] = entry
        base_binary.write_bytes(binary)

        extract_dir = tmp_path / "extract"
        extract_all(str(base_binary), str(extract_dir), source_version="1.2.3")

        checksum = hashlib.sha256(base_binary.read_bytes()).hexdigest()
        patch_dir = tmp_path / "patch"
        write_patch_manifest(
            patch_dir,
            make_patch_manifest(
                targets={
                    "versions": ["1.2.3"],
                    "binary_sha256": [checksum],
                },
                operations=[
                    {
                        "type": "replace_string",
                        "path": "app.js",
                        "find": "console.log('before');",
                        "replace": "console.log('after');",
                    }
                ],
            ),
        )

        apply_patch(patch_dir, extract_dir)

        rebuilt_binary = tmp_path / "claude-patched"
        pack_bundle(str(extract_dir), str(rebuilt_binary), str(base_binary))

        roundtrip_extract_dir = tmp_path / "roundtrip"
        extract_all(str(rebuilt_binary), str(roundtrip_extract_dir))

        assert (roundtrip_extract_dir / "app.js").read_text(encoding="utf-8") == "console.log('after');\n"
