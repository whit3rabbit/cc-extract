from cc_extractor.binary_patcher.prompts import OVERLAY_MARKERS, apply_prompts


WEBFETCH_TAIL = "- For GitHub URLs, prefer using the gh CLI via Bash instead (e.g., gh pr view, gh issue view, gh api)."


def build_fixture():
    webfetch = f"""let WEBFETCH=`Fetches and processes URLs.

  - HTTP URLs are upgraded to HTTPS
  - {WEBFETCH_TAIL}`;"""
    skill = """function getSkill(){return `Execute a skill.

If you see a <${TAG}> tag in the current conversation turn, the skill has ALREADY been loaded - follow the instructions directly instead of calling this tool again`}"""
    return webfetch + "\n\n" + skill


def test_apply_prompts_splices_overlay_after_tail_anchor():
    result = apply_prompts(build_fixture(), {"webfetch": "Use zai-cli read instead."})

    assert result.replaced_targets == ["webfetch"]
    assert result.missing == []
    assert OVERLAY_MARKERS["start"] in result.js
    assert "Use zai-cli read instead." in result.js
    assert OVERLAY_MARKERS["end"] in result.js
    assert result.js.index(OVERLAY_MARKERS["start"]) > result.js.index(WEBFETCH_TAIL)


def test_apply_prompts_replaces_existing_block_instead_of_duplicating():
    first = apply_prompts(build_fixture(), {"webfetch": "first overlay text"})
    second = apply_prompts(first.js, {"webfetch": "second overlay text"})

    assert second.js.count("cc-mirror:provider-overlay start") == 1
    assert second.js.count("cc-mirror:provider-overlay end") == 1
    assert "second overlay text" in second.js
    assert "first overlay text" not in second.js


def test_apply_prompts_handles_multiple_overlay_keys():
    result = apply_prompts(build_fixture(), {"webfetch": "web overlay", "skill": "skill overlay"})

    assert sorted(result.replaced_targets) == ["skill", "webfetch"]
    assert "web overlay" in result.js
    assert "skill overlay" in result.js


def test_apply_prompts_records_missing_anchors_without_throwing():
    result = apply_prompts(build_fixture().replace(WEBFETCH_TAIL, ""), {"webfetch": "will not splice"})

    assert result.replaced_targets == []
    assert result.missing == ["webfetch"]
    assert "will not splice" not in result.js


def test_apply_prompts_records_unknown_keys_as_missing():
    result = apply_prompts(build_fixture(), {"main": "overlay text"})

    assert result.replaced_targets == []
    assert result.missing == ["main"]


def test_apply_prompts_skips_empty_overlay_text():
    fixture = build_fixture()
    result = apply_prompts(fixture, {"webfetch": "   \n  \t\n"})

    assert result.replaced_targets == []
    assert result.missing == []
    assert result.js == fixture


def test_apply_prompts_escapes_template_literal_overlay_text():
    result = apply_prompts(build_fixture(), {"webfetch": "Use `npx zai-cli` to ${run} commands"})

    assert result.replaced_targets == ["webfetch"]
    assert "Use \\`npx zai-cli\\` to \\${run} commands" in result.js
    assert "Use `npx zai-cli`" not in result.js


def test_apply_prompts_empty_overlays_noop():
    fixture = build_fixture()
    result = apply_prompts(fixture, {})

    assert result.replaced_targets == []
    assert result.missing == []
    assert result.js == fixture
