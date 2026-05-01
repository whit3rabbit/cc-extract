"""Inject custom themes into Claude Code's theme registry.

Adapter over cc_extractor.binary_patcher.theme.
"""

from ..binary_patcher.theme import apply_theme, themes_from_config
from . import Patch, PatchContext, PatchOutcome
from ._pinned_default import DEFAULT_VERSION_RANGES


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    themes = themes_from_config(dict(ctx.config) if ctx.config else None)
    if not themes:
        return PatchOutcome(js=js, status="skipped")
    result = apply_theme(js, themes)
    if result.replaced:
        return PatchOutcome(js=result.js, status="applied")
    return PatchOutcome(js=result.js, status="skipped")


PATCH = Patch(
    id="themes",
    name="Custom themes",
    group="ui",
    versions_supported=">=2.0.0,<3",
    versions_tested=DEFAULT_VERSION_RANGES,
    apply=_apply,
    description="Inject custom theme entries into Claude Code's theme registry.",
)
