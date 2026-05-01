"""Explicit registry of `cc_extractor.patches` Patch objects."""

from typing import Dict

from . import Patch
from . import hide_startup_banner, show_more_items

REGISTRY: Dict[str, Patch] = {
    hide_startup_banner.PATCH.id: hide_startup_banner.PATCH,
    show_more_items.PATCH.id: show_more_items.PATCH,
}


def get_patch(patch_id: str) -> Patch:
    if patch_id not in REGISTRY:
        raise KeyError(f"unknown patch: {patch_id!r}")
    return REGISTRY[patch_id]


def registered_ids() -> tuple:
    return tuple(REGISTRY.keys())
