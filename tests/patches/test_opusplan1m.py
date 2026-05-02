import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.opusplan1m import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("opusplan1m")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert 'currentModel()==="opusplan[1m]"' in outcome.js
    assert '"opusplan","opusplan[1m]"' in outcome.js
    assert 'if(A==="opusplan[1m]")return"Opus 4.6 in plan mode, else Sonnet 4.6 (1M context)"' in outcome.js
    assert 'if(A==="opusplan[1m]")return"Opus Plan 1M"' in outcome.js
    assert 'value:"opusplan[1m]"' in outcome.js


def test_metadata():
    assert PATCH.id == "opusplan1m"
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
