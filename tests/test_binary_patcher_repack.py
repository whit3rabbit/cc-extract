import pytest

from cc_extractor.binary_patcher import replace_entry_js
from cc_extractor.binary_patcher.pe_resize import PeNotLastSectionError, repack_pe
from cc_extractor.bun_extract import parse_bun_binary
from cc_extractor.bun_extract.constants import OFFSETS_SIZE
from tests.helpers.bun_fixture import build_bun_fixture


THREE_MODULES = [
    {"name": "src/header.js", "content": "HHHHHHHHHH"},
    {"name": "src/cli.js", "content": "CCCCCCCCCCCCCCCC"},
    {"name": "src/footer.js", "content": "FFFFFFFFFFFFFFFFFFFF"},
]


def _content(data, info, index):
    module = info.modules[index]
    return data[info.data_start + module.cont_off : info.data_start + module.cont_off + module.cont_len].decode("utf-8")


@pytest.mark.parametrize("platform", ["elf", "macho", "pe"])
@pytest.mark.parametrize(
    ("new_content", "expected_delta"),
    [
        (b"X" * 64, 48),
        (b"xy", -14),
        (b"1234567890ABCDEF", 0),
    ],
)
def test_replace_entry_js_resizes_entry(platform, new_content, expected_delta):
    fixture = build_bun_fixture(
        platform=platform,
        module_struct_size=52,
        modules=THREE_MODULES,
        entry_point_id=1,
    )
    info = parse_bun_binary(fixture["buf"])

    result = replace_entry_js(fixture["buf"], info, new_content)

    reparsed = parse_bun_binary(result.buf)
    assert result.delta == expected_delta
    assert reparsed.modules[0].name == "src/header.js"
    assert reparsed.modules[1].name == "src/cli.js"
    assert reparsed.modules[2].name == "src/footer.js"
    assert _content(result.buf, reparsed, 0) == "HHHHHHHHHH"
    assert _content(result.buf, reparsed, 1) == new_content.decode("utf-8")
    assert _content(result.buf, reparsed, 2) == "FFFFFFFFFFFFFFFFFFFF"


@pytest.mark.parametrize("platform", ["elf", "macho", "pe"])
def test_replace_entry_js_resizes_v36_module_table(platform):
    fixture = build_bun_fixture(
        platform=platform,
        module_struct_size=36,
        modules=THREE_MODULES,
        entry_point_id=1,
    )
    info = parse_bun_binary(fixture["buf"])

    result = replace_entry_js(fixture["buf"], info, b"Z" * 40)

    reparsed = parse_bun_binary(result.buf)
    assert reparsed.module_size == 36
    assert _content(result.buf, reparsed, 0) == "HHHHHHHHHH"
    assert _content(result.buf, reparsed, 1) == "Z" * 40
    assert _content(result.buf, reparsed, 2) == "FFFFFFFFFFFFFFFFFFFF"


@pytest.mark.parametrize(("entry_point_id", "new_content"), [(0, b"NEWHEADER123456789012"), (2, b"NEWFOOTER")])
def test_replace_entry_js_handles_entry_position(entry_point_id, new_content):
    fixture = build_bun_fixture(
        platform="elf",
        module_struct_size=52,
        modules=THREE_MODULES,
        entry_point_id=entry_point_id,
    )
    info = parse_bun_binary(fixture["buf"])

    result = replace_entry_js(fixture["buf"], info, new_content)

    reparsed = parse_bun_binary(result.buf)
    assert _content(result.buf, reparsed, entry_point_id) == new_content.decode("utf-8")


def test_replace_entry_js_strips_macho_code_signature():
    fixture = build_bun_fixture(
        platform="macho",
        module_struct_size=52,
        modules=THREE_MODULES,
        entry_point_id=1,
        with_code_signature=True,
        trailing_padding=256,
    )
    info = parse_bun_binary(fixture["buf"])
    assert info.has_code_signature is True

    result = replace_entry_js(fixture["buf"], info, b"Y" * 32)

    reparsed = parse_bun_binary(result.buf)
    assert result.signature_invalidated is True
    assert result.signature_stripped is True
    assert reparsed.has_code_signature is False
    assert _content(result.buf, reparsed, 1) == "Y" * 32


def test_pe_last_section_guard_rejects_not_last_bun_section():
    fixture = build_bun_fixture(
        platform="pe",
        module_struct_size=52,
        modules=THREE_MODULES,
        entry_point_id=1,
        pe_extra_section_after=True,
    )
    info = parse_bun_binary(fixture["buf"])

    with pytest.raises(PeNotLastSectionError):
        repack_pe(fixture["buf"], info, b"hi", b"\x00" * OFFSETS_SIZE)
