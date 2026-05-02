import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.token_count_rounding import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies_default(cli_js_synthetic):
    js = cli_js_synthetic("token-count-rounding")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert "Math.round((inputTokens+outputTokens)/1000)*1000" in outcome.js


def test_synthetic_applies_config(cli_js_synthetic):
    js = cli_js_synthetic("token-count-rounding")
    outcome = PATCH.apply(
        js,
        PatchContext(
            claude_version=None,
            config={"settings": {"misc": {"tokenCountRounding": 50}}},
        ),
    )
    assert outcome.status == "applied"
    assert "Math.round((inputTokens+outputTokens)/50)*50" in outcome.js


def test_metadata():
    assert PATCH.id == "token-count-rounding"
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
