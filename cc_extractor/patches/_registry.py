"""Explicit registry of `cc_extractor.patches` Patch objects."""

from typing import Dict

from . import Patch
from . import (
    auto_accept_plan_mode,
    hide_ctrl_g,
    hide_startup_banner,
    hide_startup_clawd,
    model_customizations,
    show_more_items,
    suppress_line_numbers,
)

REGISTRY: Dict[str, Patch] = {
    auto_accept_plan_mode.PATCH.id: auto_accept_plan_mode.PATCH,
    hide_ctrl_g.PATCH.id: hide_ctrl_g.PATCH,
    hide_startup_banner.PATCH.id: hide_startup_banner.PATCH,
    hide_startup_clawd.PATCH.id: hide_startup_clawd.PATCH,
    model_customizations.PATCH.id: model_customizations.PATCH,
    show_more_items.PATCH.id: show_more_items.PATCH,
    suppress_line_numbers.PATCH.id: suppress_line_numbers.PATCH,
}


def get_patch(patch_id: str) -> Patch:
    if patch_id not in REGISTRY:
        raise KeyError(f"unknown patch: {patch_id!r}")
    return REGISTRY[patch_id]


def registered_ids() -> tuple:
    return tuple(REGISTRY.keys())
