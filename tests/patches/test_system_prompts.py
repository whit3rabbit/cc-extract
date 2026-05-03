from cc_extractor.patches.system_prompts import apply_system_prompts


def test_apply_system_prompts_escapes_js_string_line_breaks_and_delimiter():
    content = 'const prompt="OLD";'
    custom_content = 'x";globalThis.pwned=1;//\r\u2028\u2029\0\\'
    patched, results = apply_system_prompts(
        content,
        "2.1.0",
        [
            {
                "id": "test-prompt",
                "name": "Test Prompt",
                "pieces": ["OLD"],
                "custom_content": custom_content,
            }
        ],
    )

    assert results[0].applied is True
    assert '\r' not in patched
    assert '\u2028' not in patched
    assert '\u2029' not in patched
    assert '\0' not in patched
    assert 'x\\";globalThis.pwned=1;//\\r\\u2028\\u2029\\u0000\\\\' in patched


def test_apply_system_prompts_escapes_template_literal_interpolation():
    content = "const prompt=`OLD`;"
    patched, results = apply_system_prompts(
        content,
        "2.1.0",
        [
            {
                "id": "test-prompt",
                "name": "Test Prompt",
                "pieces": ["OLD"],
                "custom_content": "Use ${danger} and `ticks`\u2028",
            }
        ],
    )

    assert results[0].applied is True
    assert "\\${danger}" in patched
    assert "\\`ticks\\`" in patched
    assert "\u2028" not in patched
    assert "\\u2028" in patched
