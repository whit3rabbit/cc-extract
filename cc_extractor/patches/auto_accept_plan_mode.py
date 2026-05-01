"""Auto-accept the 'Ready to code?' plan-mode prompt."""

import re

from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    ready_idx = js.find('title:"Ready to code?"')
    if ready_idx == -1:
        return PatchOutcome(js=js, status="missed")
    if re.search(r"[$\w]+(?:\.current)?\(\"yes-accept-edits\"\);return null;return", js):
        return PatchOutcome(js=js, status="skipped")
    after = js[ready_idx:ready_idx + 3000]
    accept_func = None
    for pattern in (
        r"onChange:\([$\w]+\)=>([$\w]+)\([$\w]+\),onCancel",
        r"onChange:([$\w]+),onCancel",
        r"onChange:\([$\w]+\)=>void ([$\w]+)\.current\([$\w]+\),onCancel",
    ):
        match = re.search(pattern, after)
        if match:
            accept_func = match.group(1)
            if ".current" not in accept_func and "current" in pattern:
                accept_func += ".current"
            break
    if not accept_func:
        return PatchOutcome(js=js, status="missed")
    before_start = max(0, ready_idx - 500)
    before = js[before_start:ready_idx]
    return_idx = before.rfind("return ")
    if return_idx == -1:
        return PatchOutcome(js=js, status="missed")
    insert_at = before_start + return_idx
    insertion = f'{accept_func}("yes-accept-edits");return null;'
    new_js = js[:insert_at] + insertion + js[insert_at:]
    return PatchOutcome(js=new_js, status="applied")


PATCH = Patch(
    id="auto-accept-plan-mode",
    name="Auto-accept plan mode",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
)
