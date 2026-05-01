"""Placeholder L4 snapshot test for hide-startup-banner.

The test body captures the variant's startup screen (via whatever TUI
capture mechanism the executing harness supplies) and asserts the result
matches snapshots/hide_startup_banner.txt. The actual capture call
depends on the TUI MCP integration; this skeleton exists so the harness
shape is exercised without committing to a specific MCP API yet.
"""

import os

import pytest

from tests.patches_behavioral.conftest import assert_snapshot


pytestmark = pytest.mark.skipif(
    os.environ.get("CC_EXTRACTOR_TUI_MCP") != "1",
    reason="CC_EXTRACTOR_TUI_MCP=1 not set",
)


def test_banner_hidden(variant_factory):
    cmd, env = variant_factory(
        "smoke-banner",
        claude_version="2.1.123",  # adjust to a version present in the index
        tweak_ids=["hide-startup-banner"],
    )
    pytest.skip(
        "L4 capture mechanism not wired up yet; this test is a skeleton. "
        "Wire to TUI MCP in a follow-up; for now assert_snapshot is unused."
    )
    # Future:
    # screen = capture_via_tui_mcp(cmd, env, settle_timeout=3.0)
    # assert_snapshot(screen, "hide_startup_banner")
