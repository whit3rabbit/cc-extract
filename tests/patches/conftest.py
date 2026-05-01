"""Shared fixtures and helpers for patch tests."""

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List

import pytest

from cc_extractor.bun_extract import parse_bun_binary
from cc_extractor.download_index import load_download_index
from cc_extractor.downloader import download_binary
from cc_extractor.patches._versions import resolve_range_to_version


def resolve_tested_versions(patch) -> List[str]:
    """Resolve every range in patch.versions_tested to its highest concrete
    version in the local download index. Returns deduplicated list. Ranges
    that resolve to None are dropped (parametrize will skip those buckets
    via pytest.skip in the test body if needed)."""
    index = load_download_index()
    out: List[str] = []
    for range_expr in patch.versions_tested:
        version = resolve_range_to_version(range_expr, index=index)
        if version is not None and version not in out:
            out.append(version)
    return out


_CLI_JS_CACHE = {}


def _extract_cli_js(binary_path: Path) -> str:
    """Extract the cli.js module bytes from a Claude Code Bun binary.

    Field naming: BunModule uses `cont_off` / `cont_len`, not `data_offset` /
    `data_size`. Module content lives at `info.data_start + module.cont_off`.
    """
    data = binary_path.read_bytes()
    info = parse_bun_binary(data)
    for module in info.modules:
        if module.name and module.name.endswith("cli.js"):
            start = info.data_start + module.cont_off
            return data[start : start + module.cont_len].decode("utf-8", errors="replace")
    raise RuntimeError(f"cli.js not found inside {binary_path}")


@pytest.fixture(scope="session")
def cli_js_real() -> Callable[[str], str]:
    def loader(version: str) -> str:
        if version in _CLI_JS_CACHE:
            return _CLI_JS_CACHE[version]
        binary_path = download_binary(version=version)
        js = _extract_cli_js(Path(binary_path))
        _CLI_JS_CACHE[version] = js
        return js
    return loader


@pytest.fixture(scope="session")
def parse_js() -> Callable[[str], None]:
    node = shutil.which("node")
    if node is None:
        def _skip(_js: str) -> None:
            pytest.skip("node not on PATH; skipping L2 parse check")
        return _skip

    def runner(js: str) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fp:
            fp.write(js)
            tmp_path = fp.name
        try:
            result = subprocess.run(
                [node, "--check", tmp_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise AssertionError(
                    f"node --check failed: {result.stderr.strip() or result.stdout.strip()}"
                )
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    return runner


@pytest.fixture
def cli_js_synthetic():
    from tests.patches.fixtures.synthetic import SYNTHETIC

    def loader(patch_id: str) -> str:
        if patch_id not in SYNTHETIC:
            raise KeyError(f"no synthetic snippet for patch {patch_id!r}")
        return SYNTHETIC[patch_id]
    return loader
