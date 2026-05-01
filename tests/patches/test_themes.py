import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.themes import PATCH
from tests.patches.conftest import resolve_tested_versions


THEMES = [
    {"id": "dark", "name": "Dark mode", "colors": {"bashBorder": "#fff"}},
    {"id": "provider", "name": "Provider", "colors": {"bashBorder": "#daa"}},
]


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("themes")
    outcome = PATCH.apply(
        js,
        PatchContext(
            claude_version=None,
            config={"settings": {"themes": THEMES}},
        ),
    )
    assert outcome.status == "applied"
    assert 'case"provider":return{"bashBorder":"#daa"}' in outcome.js


def test_skipped_when_no_themes_in_config(cli_js_synthetic):
    js = cli_js_synthetic("themes")
    outcome = PATCH.apply(js, PatchContext(claude_version=None, config={}))
    assert outcome.status == "skipped"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l1(cli_js_real, version):
    outcome = PATCH.apply(
        cli_js_real(version),
        PatchContext(
            claude_version=version,
            config={"settings": {"themes": THEMES}},
        ),
    )
    assert outcome.status == "applied"


@pytest.mark.parametrize("version", resolve_tested_versions(PATCH))
def test_real_l2(cli_js_real, version, parse_js):
    js = cli_js_real(version)
    try:
        parse_js(js)
    except AssertionError:
        pytest.skip(f"original extracted JS for {version} does not parse; skipping L2 test")
    outcome = PATCH.apply(
        js,
        PatchContext(
            claude_version=version,
            config={"settings": {"themes": THEMES}},
        ),
    )
    parse_js(outcome.js)
