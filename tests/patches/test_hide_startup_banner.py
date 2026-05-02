import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.hide_startup_banner import PATCH


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("hide-startup-banner")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert "isBeforeFirstMessage" not in outcome.js or "return null;" in outcome.js


def test_realistic_function_anchor_skips_terminal_helper_false_positive():
    js = (
        'function abH(){return terminal==="Apple_Terminal"}'
        + ("x" * 6000)
        + 'function qDH(){let terminal="Apple_Terminal";return "Welcome to Claude Code"}'
    )
    outcome = PATCH.apply(js, PatchContext(claude_version="2.1.123"))
    assert outcome.status == "applied"
    assert 'function abH(){return terminal==="Apple_Terminal"}' in outcome.js
    assert 'function qDH(){return null;}' in outcome.js


def test_metadata():
    assert PATCH.id == "hide-startup-banner"
    assert PATCH.group == "ui"
    assert PATCH.versions_tested  # non-empty


@pytest.fixture
def real_js_versions():
    from tests.patches.conftest import resolve_tested_versions
    return resolve_tested_versions(PATCH)


def test_real_l1_anchor_matches(cli_js_real, real_js_versions):
    if not real_js_versions:
        pytest.skip("no resolved versions")
    for version in real_js_versions:
        js = cli_js_real(version)
        outcome = PATCH.apply(js, PatchContext(claude_version=version))
        assert outcome.status == "applied", (
            f"hide-startup-banner did not apply against {version}"
        )


def test_real_l2_patched_js_parses(cli_js_real, real_js_versions, parse_js):
    if not real_js_versions:
        pytest.skip("no resolved versions")
    for version in real_js_versions:
        js = cli_js_real(version)
        # Skip L2 test if the original JS doesn't parse (extraction issue, not patch issue)
        try:
            parse_js(js)
        except AssertionError:
            pytest.skip(f"original extracted JS for {version} does not parse; skipping L2 test")
        outcome = PATCH.apply(js, PatchContext(claude_version=version))
        parse_js(outcome.js)
