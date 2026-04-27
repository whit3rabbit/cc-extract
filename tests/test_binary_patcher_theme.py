import pytest

from cc_extractor.binary_patcher.theme import ThemeAnchorNotFound, apply_theme


THEMES = [
    {"id": "dark", "name": "Dark mode", "colors": {"bashBorder": "#fff", "autoAccept": "#0f0", "text": "#aaa"}},
    {"id": "zai-gold", "name": "Z.ai gold", "colors": {"bashBorder": "#daa", "autoAccept": "#fda", "text": "#bbb"}},
]

NEW_FORMAT_FIXTURE = "\n".join(
    [
        'function getNames(){return{"dark":"Dark mode","light":"Light mode","zaiGold":"Auto Z.ai gold"}}',
        'const themeOptions=[{label:"Dark mode",value:"dark"},{label:"Light mode",value:"light"}];',
        'function pickTheme(A){switch(A){case"light":return LX9;case"dark":return CX9;default:return CX9}}',
    ]
)

OLD_FORMAT_FIXTURE = "\n".join(
    [
        'function getNames(){return{"dark":"Dark mode","light":"Light mode"}}',
        'const themeOptions=[{label:"Dark mode",value:"dark"},{label:"Light mode",value:"light"}];',
        'function pickTheme(A){switch(A){case"dark":return{"autoAccept":"#0f0","bashBorder":"#fff","text":"#aaa"};default:return{"autoAccept":"#0f0","bashBorder":"#fff","text":"#aaa"}}}',
    ]
)


def test_apply_theme_rewrites_new_format_bundle():
    result = apply_theme(NEW_FORMAT_FIXTURE, THEMES)

    assert result.replaced == 3
    assert 'case"dark":return{"bashBorder":"#fff"' in result.js
    assert 'case"zai-gold":return{"bashBorder":"#daa"' in result.js
    assert '[{"label":"Dark mode","value":"dark"},{"label":"Z.ai gold","value":"zai-gold"}]' in result.js
    assert 'return{"dark":"Dark mode","zai-gold":"Z.ai gold"}' in result.js


def test_apply_theme_rewrites_old_format_bundle():
    result = apply_theme(OLD_FORMAT_FIXTURE, THEMES)

    assert result.replaced == 3
    assert 'case"zai-gold":return{"bashBorder":"#daa"' in result.js


def test_apply_theme_noop_for_empty_theme_list():
    result = apply_theme(NEW_FORMAT_FIXTURE, [])

    assert result.replaced == 0
    assert result.js == NEW_FORMAT_FIXTURE


@pytest.mark.parametrize(
    ("broken", "anchor"),
    [
        (NEW_FORMAT_FIXTURE.replace('function pickTheme(A){switch(A){case"light":return LX9;case"dark":return CX9;default:return CX9}}', "/* removed */"), "switch"),
        (NEW_FORMAT_FIXTURE.replace('const themeOptions=[{label:"Dark mode",value:"dark"},{label:"Light mode",value:"light"}];', "/* removed */"), "objArr"),
        (NEW_FORMAT_FIXTURE.replace('function getNames(){return{"dark":"Dark mode","light":"Light mode","zaiGold":"Auto Z.ai gold"}}', "/* removed */"), "obj"),
    ],
)
def test_apply_theme_throws_anchor_not_found(broken, anchor):
    with pytest.raises(ThemeAnchorNotFound) as exc:
        apply_theme(broken, THEMES)

    assert exc.value.anchor == anchor
