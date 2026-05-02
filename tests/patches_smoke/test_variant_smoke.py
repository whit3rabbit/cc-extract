"""L3 smoke: build a default-tweak variant against each resolved version
and verify the resulting binary boots cleanly.

Gated: skipped unless CC_EXTRACTOR_REAL_BINARY=1.
"""

import os
import subprocess

import pytest

from cc_extractor.download_index import load_download_index
from cc_extractor.patches._versions import resolve_range_to_version
from tests.patches._pinned import DEFAULT_VERSION_RANGES


pytestmark = pytest.mark.skipif(
    os.environ.get("CC_EXTRACTOR_REAL_BINARY") != "1",
    reason="CC_EXTRACTOR_REAL_BINARY=1 not set",
)


def _resolved_versions():
    index = load_download_index()
    out = []
    for range_expr in DEFAULT_VERSION_RANGES:
        version = resolve_range_to_version(range_expr, index=index)
        if version is not None and version not in out:
            out.append(version)
    return out


@pytest.mark.parametrize("version", _resolved_versions())
def test_variant_boots(version, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = {**os.environ, "CC_EXTRACTOR_WORKSPACE": str(workspace)}

    cmd = [
        ".venv/bin/python",
        "main.py",
        "variant",
        "create",
        "--name",
        f"smoke-{version.replace('.', '-')}",
        "--provider",
        "ccrouter",
        "--claude-version",
        version,
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, f"variant create failed: {proc.stderr}"

    run_cmd = [
        ".venv/bin/python", "main.py", "variant", "run",
        f"smoke-{version.replace('.', '-')}", "--", "--version",
    ]
    proc = subprocess.run(run_cmd, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"variant run failed: {proc.stderr}"
    assert proc.stdout.strip(), "expected version output, got empty stdout"
