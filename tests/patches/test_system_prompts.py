from ccsilo.patches.system_prompts import apply_system_prompts


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


def test_apply_system_prompts_interpolates_version_and_build_time():
    build_time = "2025-12-09T19:43:43Z"
    content = f'const build=BUILD_TIME:"{build_time}";const prompt="OLD 2.1.0 {build_time}";'
    patched, results = apply_system_prompts(
        content,
        "2.1.0",
        [
            {
                "id": "test-prompt",
                "name": "Test Prompt",
                "pieces": ["OLD <<CCVERSION>> <<BUILD_TIME>>"],
                "custom_content": "NEW <<CCVERSION>> <<BUILD_TIME>>",
            }
        ],
    )

    assert results[0].applied is True
    assert f"NEW 2.1.0 {build_time}" in patched


def test_apply_system_prompts_preserves_mapped_template_interpolations():
    content = "const prompt=`Call ${J$$()} now`;"
    patched, results = apply_system_prompts(
        content,
        "2.1.0",
        [
            {
                "id": "test-prompt",
                "name": "Test Prompt",
                "pieces": ["Call ${", "()} now"],
                "identifiers": [0],
                "identifierMap": {"0": "TASK_TOOL_NAME"},
                "custom_content": "Use ${TASK_TOOL_NAME()} and ${danger} with `ticks`",
            }
        ],
    )

    assert results[0].applied is True
    assert "${J$$()}" in patched
    assert "\\${danger}" in patched
    assert "\\`ticks\\`" in patched


def test_apply_system_prompts_invalid_pieces_fail_cleanly():
    content = 'const prompt="OLD";'
    patched, results = apply_system_prompts(
        content,
        "2.1.0",
        [
            {
                "id": "test-prompt",
                "name": "Test Prompt",
                "pieces": "OLD",
                "custom_content": "NEW",
            }
        ],
    )

    assert patched == content
    assert results[0].failed is True
    assert "pieces must be a non-empty list of strings" in results[0].details
