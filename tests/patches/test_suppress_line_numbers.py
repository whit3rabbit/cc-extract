import pytest

from cc_extractor.patches import PatchContext
from cc_extractor.patches.suppress_line_numbers import PATCH
from tests.patches.conftest import resolve_tested_versions


def test_synthetic_applies(cli_js_synthetic):
    js = cli_js_synthetic("suppress-line-numbers")
    outcome = PATCH.apply(js, PatchContext(claude_version=None))
    assert outcome.status == "applied"
    assert "return C}function next" in outcome.js


def test_linux_2_1_128_indexof_helper_applies():
    js = """function GN$({content:H,startLine:$}){if(!H)return"";let q=[],K=$,_=0,A=H.indexOf(`
`);while(A!==-1)q.push(Pqq(H.slice(_,A),K++)),_=A+1,A=H.indexOf(`
`,_);return q.push(Pqq(H.slice(_),K)),q.join(`
`)}function Pqq(H,$){let q=H.endsWith("\\r")?H.slice(0,-1):H;return`${$}\t${q}`}function next(){}"""
    outcome = PATCH.apply(js, PatchContext(claude_version="2.1.128"))

    assert outcome.status == "applied"
    assert 'function GN$({content:H,startLine:$}){if(!H)return"";return H}' in outcome.js
    assert "function next(){}" in outcome.js


def test_indexof_helper_with_setup_call_applies_without_invalid_let_return():
    js = """function sN8(){return!G$("tengu_compact_line_prefix_killswitch",!1)}function uk$({content:H,startLine:$}){if(!H)return"";let q=sN8(),K=[],_=$,A=0,z=H.indexOf(`
`);while(z!==-1)K.push(n8q(H.slice(A,z),_++,q)),A=z+1,z=H.indexOf(`
`,A);return K.push(n8q(H.slice(A),_,q)),K.join(`
`)}function n8q(H,$,q){let K=H.endsWith("\\r")?H.slice(0,-1):H;if(q)return`${$}\t${K}`;let _=String($);return _.length>=6?`${_}\\u2192${K}`:`${_.padStart(6," ")}\\u2192${K}`}function next(){}"""
    outcome = PATCH.apply(js, PatchContext(claude_version="2.1.126"))

    assert outcome.status == "applied"
    assert 'function uk$({content:H,startLine:$}){if(!H)return"";return H}' in outcome.js
    assert "let q=sN8(),return H" not in outcome.js
    assert "function next(){}" in outcome.js


def test_metadata():
    assert PATCH.id == "suppress-line-numbers"
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
            f"suppress-line-numbers did not apply against {version}"
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
