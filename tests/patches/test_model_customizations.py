import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.model_customizations import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("model-customizations")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert "claude-sonnet-4-6" in outcome.js


def test_metadata():
    assert PATCH.id == "model-customizations"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l1(cli_js_real, version):
    js = cli_js_real(version)
    outcome = PATCH.apply(js, PatchContext(claude_version=version))
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
