"""L4 fixtures: build/run/capture one variant per test.

Gated: every test in this directory skips unless CC_EXTRACTOR_TUI_MCP=1.
The Codex TUI MCP is used by the developer harness, but pytest cannot call
agent-scoped MCP tools directly. These tests use a local PTY capture so they
can still assert the same terminal behavior when the gate is enabled.
"""

import os
import re
import signal
import subprocess
import time
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("CC_EXTRACTOR_TUI_MCP") != "1",
    reason="CC_EXTRACTOR_TUI_MCP=1 not set",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ANSI_RE = re.compile(
    r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))"
)


@pytest.fixture
def variant_factory(tmp_path):
    """Returns a function that builds a fresh variant in a per-test workspace
    and returns its run command (list[str]). Variants are torn down by
    pytest's tmp_path cleanup."""

    def build(name: str, claude_version: str, tweak_ids, provider: str = "ccrouter"):
        workspace = tmp_path / "workspace"
        workspace.mkdir(exist_ok=True)
        env = {**os.environ, "CC_EXTRACTOR_WORKSPACE": str(workspace)}
        cmd = [
            ".venv/bin/python", "main.py", "variant", "create",
            "--name", name,
            "--provider", provider,
            "--claude-version", claude_version,
        ] + [arg for tweak in tweak_ids for arg in ("--tweak", tweak)]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            pytest.skip(f"variant create failed: {proc.stderr}")
        return [".venv/bin/python", "main.py", "variant", "run", name, "--"], env
    return build


def capture_tui_output(cmd, env, *, settle_timeout=5.0, cols=100, rows=30) -> str:
    if os.name == "nt":
        pytest.skip("PTY capture is only available on POSIX")
    try:
        import fcntl
        import pty
        import select
        import struct
        import termios
    except ImportError as exc:
        pytest.skip(f"PTY capture unavailable: {exc}")

    local_env = dict(env)
    local_env.setdefault("TERM", "xterm-256color")
    local_env.setdefault("COLUMNS", str(cols))
    local_env.setdefault("LINES", str(rows))

    master_fd, slave_fd = pty.openpty()
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    proc = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        env=local_env,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        start_new_session=True,
    )
    os.close(slave_fd)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, os.O_NONBLOCK)
    chunks = []
    deadline = time.monotonic() + settle_timeout
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master_fd], [], [], 0.1)
            if ready:
                try:
                    data = os.read(master_fd, 65536)
                except BlockingIOError:
                    continue
                except OSError:
                    break
                if not data:
                    break
                chunks.append(data)
            if proc.poll() is not None and not ready:
                break
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=2)
        os.close(master_fd)

    raw = b"".join(chunks).decode("utf-8", "replace")
    return ANSI_RE.sub("", raw).replace("\r", "\n")


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
