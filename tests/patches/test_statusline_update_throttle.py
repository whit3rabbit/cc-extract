import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.statusline_update_throttle import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies_throttle_default(cli_js_synthetic):
    js = cli_js_synthetic("statusline-update-throttle")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert "lastCall=Pc.useRef(0)" in outcome.js
    assert "now-lastCall.current>=300" in outcome.js
    assert "X=Pc.useCallback" in outcome.js


def test_synthetic_applies_fixed_interval_config(cli_js_synthetic):
    js = cli_js_synthetic("statusline-update-throttle")
    outcome = PATCH.apply(
        js,
        PatchContext(
            claude_version=None,
            config={
                "settings": {
                    "misc": {
                        "statuslineThrottleMs": 750,
                        "statuslineUseFixedInterval": True,
                    }
                }
            },
        ),
    )
    assert outcome.status == "applied"
    assert "setInterval(()=>O(argRef.current),750)" in outcome.js
    assert "X=Pc.useCallback(()=>{},[])" in outcome.js


def test_metadata():
    assert PATCH.id == "statusline-update-throttle"
    assert PATCH.group == "ui"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l1(cli_js_real, version):
    outcome = PATCH.apply(cli_js_real(version), PatchContext(claude_version=version))
    assert outcome.status == "applied"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l2(cli_js_real, version, parse_js):
    js = cli_js_real(version)
    try:
        parse_js(js)
    except AssertionError:
        pytest.skip(f"original extracted JS for {version} does not parse; skipping L2 test")
    outcome = PATCH.apply(js, PatchContext(claude_version=version))
    parse_js(outcome.js)
