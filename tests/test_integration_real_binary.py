import os
import shutil
import subprocess
from pathlib import Path

import pytest

from cc_extractor.binary_patcher import PatchInputs, apply_patches
from cc_extractor.bun_extract import parse_bun_binary
from cc_extractor.downloader import download_binary
from cc_extractor.extractor import extract_all


RUN_ENV = "CC_EXTRACTOR_RUN_REAL_BINARY_TEST"
VERSION_ENV = "CC_EXTRACTOR_REAL_BINARY_VERSION"

pytestmark = pytest.mark.skipif(
    os.environ.get(RUN_ENV) != "1",
    reason=f"set {RUN_ENV}=1 to download, patch, and execute a real Claude Code binary",
)


def test_download_patch_and_execute_real_claude_binary(tmp_path):
    version = os.environ.get(VERSION_ENV, "latest")
    downloaded = Path(download_binary(version, out_dir=str(tmp_path / "downloads")))

    original = tmp_path / f"original-{downloaded.name}"
    patched = tmp_path / f"patched-{downloaded.name}"
    shutil.copy2(downloaded, original)
    shutil.copy2(downloaded, patched)

    original_version = _run_version(original)
    assert "Claude Code" in original_version

    config = {
        "settings": {
            "themes": [
                {
                    "id": "x",
                    "name": "X",
                    "colors": {},
                }
            ]
        }
    }
    result = apply_patches(PatchInputs(binary_path=str(patched), config=config))
    assert result.ok is True
    assert result.skipped_reason is None

    patched_version = _run_version(patched)
    assert patched_version == original_version

    data = patched.read_bytes()
    info = parse_bun_binary(data)
    entry = info.modules[info.entry_point_id]
    entry_js = data[info.data_start + entry.cont_off : info.data_start + entry.cont_off + entry.cont_len].decode("utf-8")
    assert 'case"x":return{}' in entry_js
    assert '{"label":"X","value":"x"}' in entry_js

    extract_dir = tmp_path / "extracted"
    manifest = extract_all(str(patched), str(extract_dir))
    assert manifest["entryPoint"] == entry.name
    assert (extract_dir / ".bundle_manifest.json").is_file()


def _run_version(binary_path):
    result = subprocess.run(
        [str(binary_path), "--version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()
