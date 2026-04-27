import json

from cc_extractor.binary_patcher import apply_patches
from cc_extractor.binary_patcher.index import PatchInputs
from cc_extractor.binary_patcher.prompts import OVERLAY_MARKERS
from cc_extractor.bun_extract import parse_bun_binary
from tests.helpers.bun_fixture import build_bun_fixture


THEMES = [
    {"id": "dark", "name": "Dark mode", "colors": {"bashBorder": "#fff"}},
    {"id": "zai-gold", "name": "Z.ai gold", "colors": {"bashBorder": "#daa"}},
]


def build_entry_js():
    return "\n".join(
        [
            'function getNames(){return{"dark":"Dark mode","light":"Light mode"}}',
            'const themeOptions=[{label:"Dark mode",value:"dark"},{label:"Light mode",value:"light"}];',
            'function pickTheme(A){switch(A){case"light":return LX9;case"dark":return CX9;default:return CX9}}',
            'let WEBFETCH=`Fetches and processes URLs.\n\n  - For GitHub URLs, prefer using the gh CLI via Bash instead (e.g., gh pr view, gh issue view, gh api).`;',
        ]
    )


def build_config():
    return {"settings": {"themes": THEMES}}


def write_fixture(tmp_path, platform, entry_js=None, **fixture_kwargs):
    fixture = build_bun_fixture(
        platform=platform,
        module_struct_size=52,
        modules=[
            {"name": "src/header.js", "content": "function header(){}"},
            {"name": "src/cli.js", "content": entry_js if entry_js is not None else build_entry_js()},
            {"name": "src/footer.js", "content": "function footer(){}"},
        ],
        entry_point_id=1,
        **fixture_kwargs,
    )
    path = tmp_path / f"claude-{platform}"
    path.write_bytes(fixture["buf"])
    return path


def read_entry_js(path):
    data = path.read_bytes()
    info = parse_bun_binary(data)
    entry = info.modules[info.entry_point_id]
    return data[info.data_start + entry.cont_off : info.data_start + entry.cont_off + entry.cont_len].decode("utf-8")


def test_apply_patches_unreadable_binary_returns_io_error():
    result = apply_patches(PatchInputs(binary_path="/nonexistent/path/to/claude", config=build_config()))

    assert result.ok is False
    assert result.reason == "io-error"


def test_apply_patches_successful_elf_patch_writes_changed_bytes(tmp_path):
    binary_path = write_fixture(tmp_path, "elf")

    result = apply_patches(
        PatchInputs(
            binary_path=str(binary_path),
            config=build_config(),
            overlays={"webfetch": "Use zai-cli read instead."},
        )
    )

    assert result.ok is True
    assert result.missing_prompt_keys == []
    assert result.resigned is False
    assert result.skipped_reason is None
    new_js = read_entry_js(binary_path)
    assert 'case"zai-gold":return{"bashBorder":"#daa"}' in new_js
    assert '{"label":"Z.ai gold","value":"zai-gold"}' in new_js
    assert OVERLAY_MARKERS["start"] in new_js
    assert "Use zai-cli read instead." in new_js


def test_apply_patches_missing_prompt_key_returns_success(tmp_path):
    binary_path = write_fixture(tmp_path, "elf")

    result = apply_patches(
        PatchInputs(binary_path=str(binary_path), config=build_config(), overlays={"webfetch": "web", "main": "main"})
    )

    assert result.ok is True
    assert result.missing_prompt_keys == ["main"]


def test_apply_patches_theme_anchor_failure_returns_anchor_not_found(tmp_path):
    broken = build_entry_js().replace(
        'function pickTheme(A){switch(A){case"light":return LX9;case"dark":return CX9;default:return CX9}}',
        "/* removed */",
    )
    binary_path = write_fixture(tmp_path, "elf", entry_js=broken)

    result = apply_patches(PatchInputs(binary_path=str(binary_path), config=build_config()))

    assert result.ok is False
    assert result.reason == "anchor-not-found"


def test_apply_patches_macho_growth_skips_without_writing(tmp_path):
    binary_path = write_fixture(tmp_path, "macho")
    original = binary_path.read_bytes()

    result = apply_patches(
        PatchInputs(
            binary_path=str(binary_path),
            config=build_config(),
            overlays={"webfetch": "Use zai-cli read instead."},
        )
    )

    assert result.ok is True
    assert result.skipped_reason == "macho-grow-not-supported"
    assert binary_path.read_bytes() == original


def test_apply_patches_pe_last_section_guard_returns_resize_bound_exceeded(tmp_path):
    binary_path = write_fixture(tmp_path, "pe", pe_extra_section_after=True)

    result = apply_patches(PatchInputs(binary_path=str(binary_path), config=build_config()))

    assert result.ok is False
    assert result.reason == "resize-bound-exceeded"


def test_cli_apply_binary_prints_structured_json(tmp_path, capsys):
    from cc_extractor.__main__ import main
    import sys

    binary_path = write_fixture(tmp_path, "elf")
    config_path = tmp_path / "config.json"
    overlays_path = tmp_path / "overlays.json"
    config_path.write_text(json.dumps(build_config()), encoding="utf-8")
    overlays_path.write_text(json.dumps({"webfetch": "Use zai-cli read instead."}), encoding="utf-8")

    old_argv = sys.argv
    sys.argv = [
        "cc-extractor",
        "apply-binary",
        str(binary_path),
        "--config",
        str(config_path),
        "--overlays",
        str(overlays_path),
    ]
    try:
        main()
    finally:
        sys.argv = old_argv

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["missing_prompt_keys"] == []
