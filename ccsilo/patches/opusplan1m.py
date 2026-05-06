"""Add Architect Mode model alias support."""

import re

from . import Patch, PatchContext, PatchOutcome


def _replace_first(js: str, pattern: str, replacement_fn) -> str:
    match = re.search(pattern, js)
    if not match:
        raise ValueError(pattern)
    replacement = replacement_fn(match)
    return js[:match.start()] + replacement + js[match.end():]


def _patch_mode_switch(js: str) -> str:
    return _replace_first(
        js,
        r'if\s*\(\s*([$\w]+)\(\)\s*===\s*"opusplan"\s*&&\s*([$\w]+)\s*===\s*"plan"\s*&&\s*!([$\w]+)\s*\)\s*return\s*([$\w]+)\(\);',
        lambda m: f'if(({m.group(1)}()==="opusplan"||{m.group(1)}()==="opusplan[1m]")&&{m.group(2)}==="plan"&&!{m.group(3)})return {m.group(4)}();',
    )


def _patch_alias_list(js: str) -> str:
    return _replace_first(
        js,
        r'(\["sonnet","opus","haiku",(?:"best",)?"sonnet\[1m\]",(?:"opus\[1m\]",)?"opusplan")',
        lambda m: m.group(0) + ',"opusplan[1m]"',
    )


def _patch_description(js: str) -> str:
    return _replace_first(
        js,
        r'(if\s*\(\s*([$\w]+)\s*===\s*"opusplan"\s*\)\s*return\s*"Opus((?: [^"]{0,20})?) in plan mode, else Sonnet((?: [^"]{0,20})?)";)',
        lambda m: (
            m.group(1)
            + f'if({m.group(2)}==="opusplan[1m]")return"Architect mode: planner model in plan mode, worker model otherwise";'
        ),
    )


def _patch_label(js: str) -> str:
    return _replace_first(
        js,
        r'(if\s*\(\s*([$\w]+)\s*===\s*"opusplan"\s*\)\s*return\s*"Opus Plan";)',
        lambda m: m.group(1) + f'if({m.group(2)}==="opusplan[1m]")return"Architect Mode";',
    )


def _patch_selector_options(js: str) -> str:
    match = re.search(
        r'(if\s*\(\s*([$\w]+)\s*===\s*"opusplan"\s*\)\s*return\s*(?:[$\w]+\()?\[\s*\.\.\.([$\w]+)\s*,\s*([$\w]+)\(\)\s*\]\)?;)',
        js,
    )
    if not match:
        raise ValueError("selector options")
    full_match, var_name, list_var = match.group(1), match.group(2), match.group(3)
    wrapper = re.search(rf"return\s*([$\w]+)\(\s*\[\.\.\.{re.escape(list_var)}", full_match)
    new_entry = '{value:"opusplan[1m]",label:"Architect Mode",description:"Use planner model in plan mode, worker model otherwise"}'
    return_expr = f"{wrapper.group(1)}([...{list_var},{new_entry}])" if wrapper else f"[...{list_var},{new_entry}]"
    replacement = full_match + f'if({var_name}==="opusplan[1m]")return {return_expr};'
    return js[:match.start()] + replacement + js[match.end():]


def _patch_always_show(js: str) -> str:
    match = re.search(
        r'(if\s*\(\s*[$\w]+\s*===\s*null\s*\|\|\s*([$\w]+)\.some\s*\(\s*\(\s*[$\w]+\s*\)\s*=>\s*[$\w]+\.value\s*===\s*[$\w]+\s*\)\s*\)\s*return\s*(?:[$\w]+\()?[$\w]+\)?\s*;)',
        js,
    )
    if not match:
        raise ValueError("always show")
    list_var = match.group(2)
    inject = (
        f'{list_var}.push({{value:"opusplan",label:"Architect Mode",description:"Use planner model in plan mode, worker model otherwise"}});'
        f'{list_var}.push({{value:"opusplan[1m]",label:"Architect Mode",description:"Use planner model in plan mode, worker model otherwise"}});'
    )
    return js[:match.start()] + inject + js[match.start():]


def _already_patched(js: str) -> bool:
    mode_switch = re.search(
        r'if\s*\(\s*\(\s*([$\w]+)\(\)\s*===\s*"opusplan"\s*\|\|\s*\1\(\)\s*===\s*"opusplan\[1m\]"\s*\)'
        r'\s*&&\s*[$\w]+\s*===\s*"plan"\s*&&\s*![$\w]+\s*\)\s*return\s*[$\w]+\(\);',
        js,
    )
    return bool(
        mode_switch
        and re.search(r'"opusplan"\s*,\s*"opusplan\[1m\]"', js)
        and '==="opusplan[1m]")return"Architect Mode"' in js
        and 'value:"opusplan[1m]"' in js
    )


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    if _already_patched(js):
        return PatchOutcome(js=js, status="skipped")
    try:
        new_js = _patch_mode_switch(js)
        new_js = _patch_alias_list(new_js)
        new_js = _patch_description(new_js)
        new_js = _patch_label(new_js)
        new_js = _patch_selector_options(new_js)
        new_js = _patch_always_show(new_js)
    except ValueError as exc:
        return PatchOutcome(js=js, status="missed", notes=(f"missing {exc}",))
    return PatchOutcome(js=new_js, status="applied")


PATCH = Patch(
    id="opusplan1m",
    name="Architect Mode",
    group="ui",
    versions_supported=">=2.1.0,<3",
    versions_tested=(">=2.1.0,<2.2",),
    apply=_apply,
    description="Add an Architect Mode model alias that uses a planner model in plan mode and a worker model otherwise.",
)
