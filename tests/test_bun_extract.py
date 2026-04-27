import json

import pytest

from cc_extractor.bun_extract import BunFormatError, extract_all, parse_bun_binary
from cc_extractor.bun_extract.constants import OFFSETS_SIZE, TRAILER
from cc_extractor.__main__ import inspect_binary
from cc_extractor.extractor import extract_all as extract_binary
from tests.helpers.bun_fixture import build_bun_fixture


SAMPLE_MODULES = [
    {"name": "src/entrypoints/cli.js", "content": 'console.log("hello")'},
    {"name": "src/lib/util.js", "content": "export const ok = true"},
    {"name": "node_modules/foo/index.js", "content": "module.exports = 42"},
]


def test_parse_elf_fixture():
    fixture = build_bun_fixture(platform="elf", module_struct_size=52, modules=SAMPLE_MODULES)

    info = parse_bun_binary(fixture["buf"])

    assert info.platform == "elf"
    assert info.module_size == 52
    assert info.bun_version_hint == ">=1.3.13"
    assert info.modules[0].name == "src/entrypoints/cli.js"
    assert info.data_start == fixture["expected"]["data_start"]
    assert info.data_start == info.trailer_offset - info.byte_count - OFFSETS_SIZE


def test_parse_macho_fixture():
    fixture = build_bun_fixture(
        platform="macho",
        module_struct_size=52,
        modules=SAMPLE_MODULES,
        with_code_signature=True,
        trailing_padding=1024,
    )

    info = parse_bun_binary(fixture["buf"])

    assert info.platform == "macho"
    assert info.data_start == fixture["expected"]["data_start"]
    assert info.section_offset == fixture["expected"]["section_offset"]
    assert info.has_code_signature is True
    assert info.modules[0].name == "src/entrypoints/cli.js"


def test_parse_pe_fixture():
    fixture = build_bun_fixture(platform="pe", module_struct_size=52, modules=SAMPLE_MODULES)

    info = parse_bun_binary(fixture["buf"])

    assert info.platform == "pe"
    assert info.data_start == fixture["expected"]["data_start"]
    assert len(info.modules) == 3


def test_module_table_size_36():
    fixture = build_bun_fixture(platform="elf", module_struct_size=36, modules=SAMPLE_MODULES)

    info = parse_bun_binary(fixture["buf"])

    assert info.module_size == 36
    assert info.bun_version_hint == "pre-1.3.13"
    assert info.modules[1].name == "src/lib/util.js"


def test_entry_module_detection():
    fixture = build_bun_fixture(
        platform="elf",
        module_struct_size=52,
        modules=SAMPLE_MODULES,
        entry_point_id=1,
    )

    info = parse_bun_binary(fixture["buf"])

    assert info.entry_point_id == 1
    assert info.modules[1].is_entry is True
    assert info.modules[0].is_entry is False


def test_invalid_trailer_throws_bun_format_error():
    fixture = build_bun_fixture(platform="elf", module_struct_size=52, modules=SAMPLE_MODULES)
    broken = bytearray(fixture["buf"])
    broken[-len(TRAILER) :] = b"GARBAGE GARBAGE!"

    with pytest.raises(BunFormatError):
        parse_bun_binary(bytes(broken))


def test_path_prefixes_are_stripped():
    fixture = build_bun_fixture(
        platform="elf",
        module_struct_size=52,
        modules=[
            {"name": "/$bunfs/root/src/main.js", "content": "1"},
            {"name": "$bunfs/root/lib/x.js", "content": "2"},
        ],
    )

    info = parse_bun_binary(fixture["buf"])

    assert info.modules[0].name == "src/main.js"
    assert info.modules[1].name == "lib/x.js"


def test_extract_all_writes_files_and_manifest(tmp_path):
    fixture = build_bun_fixture(platform="elf", module_struct_size=52, modules=SAMPLE_MODULES)
    info = parse_bun_binary(fixture["buf"])

    result = extract_all(fixture["buf"], info, str(tmp_path))

    assert result.manifest_path is not None
    assert (tmp_path / "src/entrypoints/cli.js").read_text() == 'console.log("hello")'
    manifest = json.loads((tmp_path / ".bundle_manifest.json").read_text())
    assert manifest["platform"] == "elf"
    assert manifest["moduleSize"] == 52
    assert manifest["entryPoint"] == "src/entrypoints/cli.js"
    assert manifest["byteCount"] == info.byte_count


def test_extract_all_refuses_path_traversal(tmp_path):
    fixture = build_bun_fixture(
        platform="elf",
        module_struct_size=52,
        modules=[{"name": "../../../etc/evil", "content": "pwned"}],
    )
    info = parse_bun_binary(fixture["buf"])

    with pytest.raises(BunFormatError):
        extract_all(fixture["buf"], info, str(tmp_path))


@pytest.mark.parametrize("platform", ["elf", "macho", "pe"])
def test_extractor_wrapper_extracts_cross_platform_fixtures(tmp_path, platform):
    fixture = build_bun_fixture(platform=platform, module_struct_size=52, modules=SAMPLE_MODULES)
    binary_path = tmp_path / f"fixture-{platform}"
    out_dir = tmp_path / f"out-{platform}"
    binary_path.write_bytes(fixture["buf"])

    manifest = extract_binary(str(binary_path), str(out_dir))

    assert manifest["platform"] == platform
    assert (out_dir / "src/entrypoints/cli.js").read_text() == 'console.log("hello")'
    assert (out_dir / ".bundle_source.json").exists()


def test_inspect_binary_json_payload(tmp_path, capsys):
    fixture = build_bun_fixture(platform="pe", module_struct_size=52, modules=SAMPLE_MODULES)
    binary_path = tmp_path / "fixture-pe"
    binary_path.write_bytes(fixture["buf"])

    payload = inspect_binary(str(binary_path), as_json=True)

    printed = json.loads(capsys.readouterr().out)
    assert payload["platform"] == "pe"
    assert printed["entryPoint"] == "src/entrypoints/cli.js"
