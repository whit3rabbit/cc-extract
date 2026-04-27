import json
import subprocess
import importlib

import pytest

from cc_extractor.binary_patcher.unpack_and_patch import (
    RUNTIME_DEPENDENCIES,
    UnpackAndPatchError,
    UnpackAndPatchInputs,
    unpack_and_patch,
)
from cc_extractor.binary_patcher.prompts import OVERLAY_MARKERS
from tests.helpers.bun_fixture import build_bun_fixture

unpack_and_patch_module = importlib.import_module("cc_extractor.binary_patcher.unpack_and_patch")


THEMES = [
    {"id": "dark", "name": "Dark mode", "colors": {"bashBorder": "#fff"}},
    {"id": "zai-gold", "name": "Z.ai gold", "colors": {"bashBorder": "#daa"}},
]

ENTRY_BODY = "\n".join(
    [
        'function getNames(){return{"dark":"Dark mode","light":"Light mode"}}',
        'const themeOptions=[{label:"Dark mode",value:"dark"},{label:"Light mode",value:"light"}];',
        'function pickTheme(A){switch(A){case"light":return LX9;case"dark":return CX9;default:return CX9}}',
        "const explorePrompt=`...lots of text...\nComplete the user's search request efficiently and report your findings clearly.`",
    ]
)


def wrap_bun_cjs(body):
    return f"// @bun @bytecode @bun-cjs\n(function(exports, require, module, __filename, __dirname) {{{body}}})"


def write_binary(tmp_path):
    fixture = build_bun_fixture(
        platform="macho",
        module_struct_size=52,
        modules=[
            {"name": "src/entrypoints/cli.js", "content": wrap_bun_cjs(ENTRY_BODY)},
            {"name": "src/lib.js", "content": "module.exports = 1;"},
        ],
        entry_point_id=0,
    )
    path = tmp_path / "claude"
    path.write_bytes(fixture["buf"])
    return path


def test_unpack_and_patch_extracts_patches_package_json_and_runs_npm(tmp_path, monkeypatch):
    binary_path = write_binary(tmp_path)
    unpacked_dir = tmp_path / "unpacked"
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(unpack_and_patch_module.subprocess, "run", fake_run)

    result = unpack_and_patch(
        UnpackAndPatchInputs(
            pristine_binary_path=str(binary_path),
            unpacked_dir=str(unpacked_dir),
            config={"settings": {"themes": THEMES}},
            overlays={"explore": "Prefer search via zai-cli."},
        )
    )

    entry_path = unpacked_dir / "src/entrypoints/cli.js"
    assert result.entry_path == str(entry_path)
    written = entry_path.read_text(encoding="latin1")
    assert not written.startswith("// @bun")
    assert 'case"zai-gold":return{"bashBorder":"#daa"}' in written
    assert OVERLAY_MARKERS["start"] in written
    package_json = json.loads((unpacked_dir / "package.json").read_text(encoding="utf-8"))
    assert package_json["dependencies"] == RUNTIME_DEPENDENCIES
    assert calls[0][0] == ["npm", "install", "--silent", "--no-audit", "--no-fund"]
    assert calls[0][1]["cwd"] == str(unpacked_dir)


def test_unpack_and_patch_wraps_npm_failure(tmp_path, monkeypatch):
    binary_path = write_binary(tmp_path)

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="network unavailable")

    monkeypatch.setattr(unpack_and_patch_module.subprocess, "run", fake_run)

    with pytest.raises(UnpackAndPatchError) as exc:
        unpack_and_patch(
            pristine_binary_path=str(binary_path),
            unpacked_dir=str(tmp_path / "unpacked"),
            config={"settings": {"themes": THEMES}},
        )

    assert exc.value.stage == "deps"


def test_unpack_and_patch_wraps_extract_failure(tmp_path):
    with pytest.raises(UnpackAndPatchError) as exc:
        unpack_and_patch(
            pristine_binary_path=str(tmp_path / "missing"),
            unpacked_dir=str(tmp_path / "unpacked"),
            config={"settings": {"themes": THEMES}},
        )

    assert exc.value.stage == "extract"
