"""Suppress per-line line number prefixes in file-read output."""

import re

from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    # First pattern: simple split and map form
    sig = re.search(
        r"\{content:([$\w]+),startLine:[$\w]+\}\)\{if\(!\1\)return\"\";"
        r"let ([$\w]+)=\1\.split\([^)]+\);",
        js,
    )
    if sig:
        replace_start = sig.end()
        end = re.search(r"\}(?=function |var |let |const |[$\w]+=[$\w]+\()", js[replace_start:])
        if end:
            new_js = js[:replace_start] + f"return {sig.group(1)}" + js[replace_start + end.start():]
            return PatchOutcome(js=new_js, status="applied")

    # Second pattern: arrow function with line number padding
    arrow = re.search(
        r"if\(([$\w]+)\.length>=\d+\)return`\$\{\1\}(?:→|\\u2192)\$\{([$\w]+)\}`;"
        r"return`\$\{\1\.padStart\(\d+,\" \"\)\}(?:→|\\u2192)\$\{\2\}`",
        js,
    )
    if arrow:
        new_js = js[:arrow.start()] + f"return {arrow.group(2)}" + js[arrow.end():]
        return PatchOutcome(js=new_js, status="applied")

    # Third pattern: newer form with yN6() helper
    newer = re.search(
        r"(\{)content:([$\w]+),startLine:([$\w]+)\}\)\{if\(!([$\w]+)\)return\"\";let ([$\w]+)=([$\w]+)\(\),",
        js,
    )
    if newer:
        # Extract the function body and replace it with simpler return
        match_end = newer.end()
        # Find the end of the function body (the closing })
        depth = 0
        pos = match_end
        while pos < len(js):
            if js[pos] == '{':
                depth += 1
            elif js[pos] == '}':
                if depth == 0:
                    break
                depth -= 1
            pos += 1
        if pos < len(js):
            # Replace with return of the content variable
            content_var = newer.group(2)
            new_js = js[:match_end] + f"return {content_var}" + js[pos:]
            return PatchOutcome(js=new_js, status="applied")

    return PatchOutcome(js=js, status="missed")


PATCH = Patch(
    id="suppress-line-numbers",
    name="Suppress line numbers in file reads",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
    description="Strip per-line line-number prefixes from file-read output.",
)
