import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.filter_scroll_escape_sequences import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies_after_header(cli_js_synthetic):
    js = cli_js_synthetic("filter-scroll-escape-sequences")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert "SCROLLING FIX PATCH START" in outcome.js
    assert outcome.js.index("SCROLLING FIX PATCH START") < outcome.js.index('console.log("ready")')


def test_synthetic_skips_if_already_applied(cli_js_synthetic):
    js = cli_js_synthetic("filter-scroll-escape-sequences")
    once = PATCH.apply(js, PatchContext(claude_version=None))
    twice = PATCH.apply(once.js, PatchContext(claude_version=None))
    assert twice.status == "skipped"
    assert twice.js.count("SCROLLING FIX PATCH START") == 1


def test_metadata():
    assert PATCH.id == "filter-scroll-escape-sequences"
    assert PATCH.group == "system"


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
