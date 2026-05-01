"""Relax agent model validation to accept arbitrary string values."""

import re

from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    # First try: spec pattern with variable enum list (e.g., z.enum(MODELS))
    zod = re.search(r",model:([$\w]+)\.enum\(([$\w]+)\)\.optional\(\)", js)
    if zod:
        # Zod pattern found: relax the enum constraint
        zod_var = zod.group(1)
        model_list_var = zod.group(2)
        new_js = js[:zod.start()] + f",model:{zod_var}.string().optional()" + js[zod.end():]

        # Now find and remove the validation check
        pattern = re.compile(
            rf"([;)}}])let\s+([$\w]+)\s*=\s*([$\w]+)\s*&&\s*typeof\s+\3\s*===\"string\""
            rf"\s*&&\s*{re.escape(model_list_var)}\.includes\(\3\)"
        )
        valid = pattern.search(new_js)
        if not valid:
            return PatchOutcome(js=js, status="missed")
        replacement = (
            f'{valid.group(1)}let {valid.group(2)}={valid.group(3)}'
            f'&&typeof {valid.group(3)}==="string"'
        )
        new_js = new_js[:valid.start()] + replacement + new_js[valid.end():]
        return PatchOutcome(js=new_js, status="applied")

    # Second try: inline enum list pattern (e.g., z.enum(["sonnet","opus"]))
    # This pattern uses \] to match the closing bracket
    inline_pattern = re.compile(r",model:([$\w]+)\.enum\(\[[^\]]*\]\)\.optional\(\)", re.DOTALL)
    inline_zod = inline_pattern.search(js)
    if inline_zod:
        zod_var = inline_zod.group(1)
        replacement = f",model:{zod_var}.string().optional()"
        new_js = js[:inline_zod.start()] + replacement + js[inline_zod.end():]
        return PatchOutcome(js=new_js, status="applied")

    # Third try: the loose (non-zod) pattern
    loose = re.sub(
        r"(let\s+[$\w]+\s*=\s*([$\w]+)\s*&&\s*typeof\s+\2\s*===\"string\")"
        r"\s*&&\s*[$\w]+\.includes\(\2\)",
        r"\1",
        js,
        count=1,
    )
    if loose != js:
        return PatchOutcome(js=loose, status="applied")

    # No patterns found
    return PatchOutcome(js=js, status="missed")


PATCH = Patch(
    id="allow-custom-agent-models",
    name="Allow custom agent models",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
)
