import json
import re
from dataclasses import dataclass


class ThemeAnchorNotFound(Exception):
    def __init__(self, anchor):
        self.anchor = anchor
        super().__init__(f"theme: failed to find {anchor} anchor in cli.js")


@dataclass
class ThemeResult:
    js: str
    replaced: int


@dataclass
class _Location:
    start: int
    end: int
    identifiers: list = None


def apply_theme(js, themes):
    themes = themes or []
    if not themes:
        return ThemeResult(js=js, replaced=0)

    locations = _find_theme_locations(js)
    new_js = js

    obj_text = "return" + _json({theme["id"]: theme["name"] for theme in themes})
    new_js = new_js[: locations["obj"].start] + obj_text + new_js[locations["obj"].end :]

    obj_arr_text = _json([{"label": theme["name"], "value": theme["id"]} for theme in themes])
    obj_delta = len(obj_text) - (locations["obj"].end - locations["obj"].start)
    obj_arr_start = locations["objArr"].start
    if locations["objArr"].start >= locations["obj"].end:
        obj_arr_start += obj_delta
    obj_arr_end = obj_arr_start + (locations["objArr"].end - locations["objArr"].start)
    new_js = new_js[:obj_arr_start] + obj_arr_text + new_js[obj_arr_end:]

    ident = (locations["switch"].identifiers or ["A"])[0]
    switch_parts = [f"switch({ident}){{"]
    for theme in themes:
        switch_parts.append(f'case"{theme["id"]}":return{_json(theme.get("colors", {}))};')
    switch_parts.append(f"default:return{_json(themes[0].get('colors', {}))};")
    switch_parts.append("}")
    switch_text = "\n".join(switch_parts)

    obj_arr_delta = len(obj_arr_text) - (locations["objArr"].end - locations["objArr"].start)
    switch_start = locations["switch"].start
    if switch_start >= locations["obj"].end:
        switch_start += obj_delta
    if switch_start >= locations["objArr"].end:
        switch_start += obj_arr_delta
    switch_end = switch_start + (locations["switch"].end - locations["switch"].start)
    new_js = new_js[:switch_start] + switch_text + new_js[switch_end:]

    return ThemeResult(js=new_js, replaced=3)


def _find_theme_locations(js):
    switch_loc = _find_switch(js)
    if switch_loc is None:
        raise ThemeAnchorNotFound("switch")

    obj_arr_match = re.search(
        r'\[(?:\.\.\.\[\],)?(?:\{"?label"?:"(?:Dark|Light|Auto|Monochrome)[^"]*","?value"?:"[^"]+"\},?)+\]',
        js,
    )
    if obj_arr_match is None:
        raise ThemeAnchorNotFound("objArr")

    obj_match = re.search(
        r'(?:return|[$\w]+=)\{(?:"?(?:[$\w-]+)"?:"(?:Auto |Dark|Light|Monochrome)[^"]*",?)+\}',
        js,
    )
    if obj_match is None:
        raise ThemeAnchorNotFound("obj")

    return {
        "switch": switch_loc,
        "objArr": _Location(obj_arr_match.start(), obj_arr_match.end()),
        "obj": _Location(obj_match.start(), obj_match.end()),
    }


def _find_switch(js):
    new_match = re.search(
        r'switch\(([$\w]+)\)\{case"(?:light|dark)":[^}]*return [$\w]+;[^}]*default:return [$\w]+\}',
        js,
    )
    if new_match is not None:
        return _Location(new_match.start(), new_match.end(), [new_match.group(1)])

    anchors = [index for index in (js.find('case"dark":return{'), js.find('case"light":return{')) if index != -1]
    if not anchors:
        return None
    anchor = min(anchors)
    before_start = max(0, anchor - 200)
    before = js[before_start:anchor]
    open_match = re.search(r"switch\(([$\w]+)\)\{\s*$", before)
    if open_match is None:
        return None

    switch_start = before_start + open_match.start()
    depth = 0
    for index in range(switch_start, min(len(js), switch_start + 50000)):
        if js[index] == "{":
            depth += 1
        elif js[index] == "}":
            depth -= 1
            if depth == 0:
                return _Location(switch_start, index + 1, [open_match.group(1)])
    return None


def _json(value):
    return json.dumps(value, separators=(",", ":"))
