import pytest

from cc_extractor.variant_tweaks import TweakPatchError, apply_variant_tweaks, env_for_tweaks


THEMES = [
    {"id": "dark", "name": "Dark mode", "colors": {"bashBorder": "#fff"}},
    {"id": "provider", "name": "Provider", "colors": {"bashBorder": "#daa"}},
]


def theme_fixture():
    return "\n".join(
        [
            'function getNames(){return{"dark":"Dark mode","light":"Light mode"}}',
            'const themeOptions=[{label:"Dark mode",value:"dark"},{label:"Light mode",value:"light"}];',
            'function pickTheme(A){switch(A){case"light":return LX9;case"dark":return CX9;default:return CX9}}',
        ]
    )


def test_apply_variant_tweaks_applies_theme_prompt_and_indicator():
    js = "\n".join(
        [
            theme_fixture(),
            'let WEBFETCH=`Fetches URLs.\\n- For GitHub URLs, prefer using the gh CLI via Bash instead (e.g., gh pr view, gh issue view, gh api).`;',
            'const version=`${pkg.VERSION} (Claude Code)`;',
        ]
    )

    result = apply_variant_tweaks(
        js,
        tweak_ids=["themes", "prompt-overlays", "patches-applied-indication"],
        config={"settings": {"themes": THEMES}},
        overlays={"webfetch": "Use provider docs."},
        provider_label="Provider",
    )

    assert result.applied == ["themes", "prompt-overlays", "patches-applied-indication"]
    assert 'case"provider":return{"bashBorder":"#daa"}' in result.js
    assert "Use provider docs." in result.js
    assert "(Claude Code, Provider variant)" in result.js


def test_curated_tweak_ports_patch_fixture_patterns():
    js = "\n".join(
        [
            'function menu({visibleOptionCount:A=5}){return A}',
            'function models(){let L=[]; L.push({value:M,label:N,description:"Custom model"});return L}',
            ',R.createElement(B,{isBeforeFirstMessage:!1}),',
            'function banner(){if(x)return"Apple_Terminal";return"Welcome to Claude Code"}',
            'function inner(){return"\\u259B\\u2588\\u2588\\u2588\\u259C"}function wrapper(){return R.createElement(inner,{})}',
            'if(v&&P)p("tengu_external_editor_hint_shown",{})',
            'function fmt({content:C,startLine:S}){if(!C)return"";let L=C.split(/\\r?\\n/);return L.map(x=>x).join("\\n")}function next(){}',
            'function plan(){return R.createElement(Box,{title:"Ready to code?",onChange:onPick,onCancel:onCancel})}',
            ',model:z.enum(MODELS).optional();let ok=K&&typeof K==="string"&&MODELS.includes(K)',
        ]
    )

    result = apply_variant_tweaks(
        js,
        tweak_ids=[
            "show-more-items-in-select-menus",
            "model-customizations",
            "hide-startup-banner",
            "hide-startup-clawd",
            "hide-ctrl-g-to-edit",
            "suppress-line-numbers",
            "auto-accept-plan-mode",
            "allow-custom-agent-models",
        ],
    )

    assert "visibleOptionCount:A=25" in result.js
    assert "claude-sonnet-4-6" in result.js
    assert "isBeforeFirstMessage" not in result.js
    assert "return null;" in result.js
    assert 'if(false)p("tengu_external_editor_hint_shown"' in result.js
    assert "return C}function next" in result.js
    assert 'onPick("yes-accept-edits");return null;return R.createElement' in result.js
    assert ",model:z.string().optional()" in result.js
    assert 'let ok=K&&typeof K==="string"' in result.js


def test_missing_curated_anchor_is_failure():
    with pytest.raises(TweakPatchError, match="failed to find anchor"):
        apply_variant_tweaks("no useful anchors", tweak_ids=["hide-ctrl-g-to-edit"])


def test_env_backed_tweaks_emit_env_without_patching_js():
    env = env_for_tweaks(
        ["context-limit", "file-read-limit", "subagent-model"],
        {
            "context_limit": "1000000",
            "file_read_limit": "90000",
            "subagent_model": "model-x",
        },
    )

    assert env["CLAUDE_CODE_CONTEXT_LIMIT"] == "1000000"
    assert env["CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS"] == "90000"
    assert env["CLAUDE_CODE_SUBAGENT_MODEL"] == "model-x"


def test_apply_variant_tweaks_warns_on_untested_version():
    import warnings

    js = ",R.createElement(B,{isBeforeFirstMessage:!1}),"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        apply_variant_tweaks(
            js,
            tweak_ids=["hide-startup-banner"],
            claude_version="1.0.0",  # not in any tested range
            force=True,  # bypass unsupported-version error so we can observe the warning
        )
    assert any("1.0.0" in str(w.message) for w in caught)
