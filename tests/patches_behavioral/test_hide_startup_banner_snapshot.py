"""L4 snapshot test for hide-startup-banner."""

import os

import pytest

from tests.patches_behavioral.conftest import assert_snapshot, capture_tui_output


pytestmark = pytest.mark.skipif(
    os.environ.get("CC_EXTRACTOR_TUI_MCP") != "1",
    reason="CC_EXTRACTOR_TUI_MCP=1 not set",
)


def test_banner_hidden(variant_factory):
    cmd, env = variant_factory(
        "smoke-banner",
        claude_version="2.1.123",
        tweak_ids=["hide-startup-banner"],
    )
    screen = capture_tui_output(cmd, env)
    compact = "".join(screen.split())

    assert compact, "expected startup screen capture"
    assert "WelcometoClaudeCode" not in compact
    assert "Choosethetextstylethatlooksbestwithyourterminal" in compact
    assert_snapshot(
        "welcome_banner=absent\n"
        "theme_selector=present\n",
        "hide_startup_banner",
    )
