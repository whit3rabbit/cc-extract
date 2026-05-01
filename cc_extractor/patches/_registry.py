"""Explicit registry of `cc_extractor.patches` Patch objects."""

from typing import Dict, List, Tuple

from . import Patch
from . import (
    allow_custom_agent_models,
    auto_accept_plan_mode,
    hide_ctrl_g,
    hide_startup_banner,
    hide_startup_clawd,
    model_customizations,
    patches_applied_indication,
    prompt_overlays,
    show_more_items,
    suppress_line_numbers,
    themes,
)

REGISTRY: Dict[str, Patch] = {
    allow_custom_agent_models.PATCH.id: allow_custom_agent_models.PATCH,
    auto_accept_plan_mode.PATCH.id: auto_accept_plan_mode.PATCH,
    hide_ctrl_g.PATCH.id: hide_ctrl_g.PATCH,
    hide_startup_banner.PATCH.id: hide_startup_banner.PATCH,
    hide_startup_clawd.PATCH.id: hide_startup_clawd.PATCH,
    model_customizations.PATCH.id: model_customizations.PATCH,
    patches_applied_indication.PATCH.id: patches_applied_indication.PATCH,
    prompt_overlays.PATCH.id: prompt_overlays.PATCH,
    show_more_items.PATCH.id: show_more_items.PATCH,
    suppress_line_numbers.PATCH.id: suppress_line_numbers.PATCH,
    themes.PATCH.id: themes.PATCH,
}


def get_patch(patch_id: str) -> Patch:
    if patch_id not in REGISTRY:
        raise KeyError(f"unknown patch: {patch_id!r}")
    return REGISTRY[patch_id]


def registered_ids() -> tuple:
    return tuple(REGISTRY.keys())


GROUP_ORDER: Tuple[str, ...] = ("ui", "thinking", "prompts", "tools", "system")


def patches_grouped() -> Dict[str, List[Patch]]:
    """Return registered patches grouped by `Patch.group`.

    Group keys appear in `GROUP_ORDER` first, then any unknown group keys
    in lexicographic order. Within each group, patches keep registry insertion
    order (the order they appear in REGISTRY).
    """
    grouped: Dict[str, List[Patch]] = {}
    for patch in REGISTRY.values():
        grouped.setdefault(patch.group, []).append(patch)
    ordered: Dict[str, List[Patch]] = {}
    for group in GROUP_ORDER:
        if group in grouped:
            ordered[group] = grouped.pop(group)
    for group in sorted(grouped):
        ordered[group] = grouped[group]
    return ordered
