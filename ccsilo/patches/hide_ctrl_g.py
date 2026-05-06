"""Hide the 'press Ctrl+G to edit' hint."""

import re

from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    match = re.search(
        r"if\(([$\w]+&&[$\w]+)\)[$\w]+\(\"tengu_external_editor_hint_shown\",",
        js,
    )
    if not match:
        return PatchOutcome(js=js, status="missed")
    new_js = js[:match.start(1)] + "false" + js[match.end(1):]
    return PatchOutcome(js=new_js, status="applied")


PATCH = Patch(
    id="hide-ctrl-g-to-edit",
    name="Hide Ctrl+G edit hint",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
    description="Hide the 'press Ctrl+G to edit' hint shown in the input footer.",
)
