"""Inject provider overlay blocks after known prompt anchors.

Adapter over cc_extractor.binary_patcher.prompts.apply_prompts.
"""

from ..binary_patcher.prompts import apply_prompts
from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    overlays = dict(ctx.overlays) if ctx.overlays else {}
    if not overlays:
        return PatchOutcome(js=js, status="skipped")
    result = apply_prompts(js, overlays)
    notes = tuple(f"prompt overlay miss: {key}" for key in result.missing)
    if result.replaced_targets:
        return PatchOutcome(js=result.js, status="applied", notes=notes)
    return PatchOutcome(js=result.js, status="skipped", notes=notes)


PATCH = Patch(
    id="prompt-overlays",
    name="Prompt overlays",
    group="prompts",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    on_miss="warn",
    apply=_apply,
    description="Inject provider-specific overlay text after known prompt anchors.",
)
