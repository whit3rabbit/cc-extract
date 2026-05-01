"""Increase visibleOptionCount in select menus.

Adapted from cc_extractor/variants/tweaks.py::_show_more_items.
"""

import re

from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    matches = list(re.finditer(r"visibleOptionCount:[$\w]+=(\d+)", js))
    if not matches:
        return PatchOutcome(js=js, status="missed")
    new_js = js
    for match in reversed(matches):
        start = match.start(1)
        new_js = new_js[:start] + "25" + new_js[match.end(1):]
    height = re.search(
        r"(\{rows:([$\w]+),columns:[$\w]+\}=[$\w]+\(\),)([$\w]+)=Math\.floor\(\2/2\)",
        new_js,
    )
    if height:
        new_js = (
            new_js[:height.start()]
            + f"{height.group(1)}{height.group(3)}={height.group(2)}"
            + new_js[height.end():]
        )
    replacements = [
        (r"Math\.max\(1,Math\.floor\(\(([$\w]+)-10\)/2\)\)", r"Math.max(1,\1-3)"),
        (r"Math\.min\(6,Math\.max\(1,([$\w]+)-3\)\)", r"Math.max(1,\1-3)"),
    ]
    for pattern, repl in replacements:
        new_js = re.sub(pattern, repl, new_js, count=1)
    return PatchOutcome(js=new_js, status="applied")


PATCH = Patch(
    id="show-more-items-in-select-menus",
    name="Show more items in select menus",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
    description="Increase visibleOptionCount to 25 so more options fit on screen at once.",
)
