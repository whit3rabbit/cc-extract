import pytest

from cc_extractor.binary_patcher.strip_bun_wrapper import BunWrapperNotFound, strip_bun_wrapper


def wrap(body):
    return f"// @bun @bytecode @bun-cjs\n(function(exports, require, module, __filename, __dirname) {{{body}}})"


def test_strip_bun_wrapper_removes_bun_cjs_wrapper():
    assert strip_bun_wrapper(wrap('console.log("hi");')) == 'console.log("hi");'


def test_strip_bun_wrapper_handles_trailing_whitespace_and_semicolon():
    assert strip_bun_wrapper(wrap('console.log("hi");') + ";\n  ") == 'console.log("hi");'


def test_strip_bun_wrapper_preserves_nested_braces():
    body = "function f(){return{a:1,b:{c:2}}}f();"
    assert strip_bun_wrapper(wrap(body)) == body


def test_strip_bun_wrapper_noop_without_wrapper():
    plain = "module.exports = { ok: true };"
    assert strip_bun_wrapper(plain) == plain


def test_strip_bun_wrapper_throws_when_close_anchor_missing():
    with pytest.raises(BunWrapperNotFound) as exc:
        strip_bun_wrapper("// @bun foo\n(function(a, b) {let x = 1;\n")

    assert exc.value.anchor == "close"


def test_strip_bun_wrapper_throws_when_open_signature_malformed():
    with pytest.raises(BunWrapperNotFound) as exc:
        strip_bun_wrapper("// @bun foo\nnotAFunctionExpression()")

    assert exc.value.anchor == "open"
