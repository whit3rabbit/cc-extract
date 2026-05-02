import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.remember_skill import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("remember-skill")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert 'register({name:"remember"' in outcome.js
    assert "Review session memories" in outcome.js
    assert "loadSessionMemory(null)" in outcome.js


def test_metadata():
    assert PATCH.id == "remember-skill"
    assert PATCH.group == "prompts"
    assert PATCH.versions_supported == ">=2.1.0,<2.1.42"


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
