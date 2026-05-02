"""L4 smoke coverage for first-wave UI/system tweak ports."""

import os

import pytest

from tests.patches_behavioral.conftest import assert_snapshot, capture_tui_output


pytestmark = pytest.mark.skipif(
    os.environ.get("CC_EXTRACTOR_TUI_MCP") != "1",
    reason="CC_EXTRACTOR_TUI_MCP=1 not set",
)


def test_first_wave_ui_patches_boot(variant_factory):
    cmd, env = variant_factory(
        "smoke-first-wave-ui",
        claude_version="2.1.123",
        tweak_ids=[
            "suppress-native-installer-warning",
            "input-box-border",
            "filter-scroll-escape-sequences",
        ],
    )
    screen = capture_tui_output(cmd, env)
    compact = "".join(screen.split())

    assert compact, "expected startup screen capture"
    assert "ClaudeCodehasswitchedfromnpmtonativeinstaller" not in compact
    assert_snapshot(
        "first_wave_ui=booted\n"
        "native_installer_warning=absent\n",
        "first_wave_ui",
    )
