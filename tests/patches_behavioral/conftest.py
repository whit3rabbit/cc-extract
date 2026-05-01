"""L4 fixtures: build/run/teardown one variant per test.

Gated: every test in this directory skips unless CC_EXTRACTOR_TUI_MCP=1.
The TUI MCP itself is not invoked from Python here; instead, this conftest
is a thin shell that prepares variants. The actual screen capture and
snapshot diff happen in test bodies (which call into the MCP via whatever
mechanism the executing harness provides — see docs/patches.md).
"""

import os
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("CC_EXTRACTOR_TUI_MCP") != "1",
    reason="CC_EXTRACTOR_TUI_MCP=1 not set",
)


@pytest.fixture
def variant_factory(tmp_path):
    """Returns a function that builds a fresh variant in a per-test workspace
    and returns its run command (list[str]). Variants are torn down by
    pytest's tmp_path cleanup."""

    def build(name: str, claude_version: str, tweak_ids):
        workspace = tmp_path / "workspace"
        workspace.mkdir(exist_ok=True)
        env = {**os.environ, "CC_EXTRACTOR_WORKSPACE": str(workspace)}
        cmd = [
            ".venv/bin/python", "main.py", "variant", "create", name,
            "--claude-version", claude_version,
        ] + [arg for tweak in tweak_ids for arg in ("--tweak", tweak)]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            pytest.skip(f"variant create failed: {proc.stderr}")
        return [".venv/bin/python", "main.py", "variant", "run", name, "--"], env
    return build


SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
SNAPSHOT_DIR.mkdir(exist_ok=True)


def assert_snapshot(actual: str, snapshot_name: str) -> None:
    """Compare `actual` to snapshots/<snapshot_name>.txt. Update with
    CC_EXTRACTOR_UPDATE_SNAPSHOTS=1."""
    path = SNAPSHOT_DIR / f"{snapshot_name}.txt"
    if os.environ.get("CC_EXTRACTOR_UPDATE_SNAPSHOTS") == "1":
        path.write_text(actual)
        return
    if not path.exists():
        path.write_text(actual)
        pytest.skip(f"snapshot created: {path}")
    expected = path.read_text()
    assert actual == expected, f"snapshot mismatch for {snapshot_name}"
