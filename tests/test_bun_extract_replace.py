import pytest

from cc_extractor.bun_extract import ModuleNotFound, SizeMismatch, parse_bun_binary, replace_module
from tests.helpers.bun_fixture import build_bun_fixture


MODULES = [
    {"name": "src/cli.js", "content": "AAAAAAAAAA"},
    {"name": "src/lib.js", "content": "BBBBBBBBBB"},
]


def _module_content(data, info, name):
    module = next(module for module in info.modules if module.name == name)
    return data[info.data_start + module.cont_off : info.data_start + module.cont_off + module.cont_len]


def test_replace_module_round_trips_same_size_content():
    fixture = build_bun_fixture(platform="elf", module_struct_size=52, modules=MODULES)
    info = parse_bun_binary(fixture["buf"])

    result = replace_module(fixture["buf"], info, "src/cli.js", b"CCCCCCCCCC")

    reparsed = parse_bun_binary(result.buf)
    assert result.signature_invalidated is False
    assert _module_content(result.buf, reparsed, "src/cli.js") == b"CCCCCCCCCC"
    assert _module_content(result.buf, reparsed, "src/lib.js") == b"BBBBBBBBBB"


def test_replace_module_accepts_bunfs_prefixed_name():
    fixture = build_bun_fixture(platform="elf", module_struct_size=52, modules=MODULES)
    info = parse_bun_binary(fixture["buf"])

    result = replace_module(fixture["buf"], info, "/$bunfs/root/src/cli.js", b"CCCCCCCCCC")

    reparsed = parse_bun_binary(result.buf)
    assert _module_content(result.buf, reparsed, "src/cli.js") == b"CCCCCCCCCC"


def test_replace_module_throws_size_mismatch():
    fixture = build_bun_fixture(platform="elf", module_struct_size=52, modules=MODULES)
    info = parse_bun_binary(fixture["buf"])

    with pytest.raises(SizeMismatch):
        replace_module(fixture["buf"], info, "src/cli.js", b"shorter")


def test_replace_module_throws_module_not_found():
    fixture = build_bun_fixture(platform="elf", module_struct_size=52, modules=MODULES)
    info = parse_bun_binary(fixture["buf"])

    with pytest.raises(ModuleNotFound):
        replace_module(fixture["buf"], info, "missing.js", b"")


def test_replace_module_flags_macho_signature_invalidation():
    fixture = build_bun_fixture(
        platform="macho",
        module_struct_size=52,
        modules=MODULES,
        with_code_signature=True,
        trailing_padding=256,
    )
    info = parse_bun_binary(fixture["buf"])

    result = replace_module(fixture["buf"], info, "src/cli.js", b"CCCCCCCCCC")

    assert result.signature_invalidated is True
