import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.auto_accept_plan_mode import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("auto-accept-plan-mode")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert 'onPick("yes-accept-edits");return null;return R.createElement' in outcome.js


def test_metadata():
    assert PATCH.id == "auto-accept-plan-mode"
    assert PATCH.group == "ui"
    assert PATCH.versions_tested  # non-empty


@pytest.fixture
def real_js_versions():
    return resolve_tested_versions(PATCH)


def test_real_l1_anchor_matches(cli_js_real, real_js_versions):
    if not real_js_versions:
        pytest.skip("no resolved versions")
    for version in real_js_versions:
        js = cli_js_real(version)
        outcome = PATCH.apply(js, PatchContext(claude_version=version))
        assert outcome.status == "applied", (
            f"auto-accept-plan-mode did not apply against {version}"
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
