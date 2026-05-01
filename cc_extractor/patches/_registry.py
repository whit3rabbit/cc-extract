"""Explicit registry of `cc_extractor.patches` Patch objects.

Each migrated patch module exposes a `PATCH` constant. This file imports
them and assembles the `REGISTRY` dict keyed by patch id. Order matters:
`apply_patches` runs requested ids in the order they appear in REGISTRY
when the caller does not specify an order.
"""

from typing import Dict

from . import Patch  # type: ignore[attr-defined]

REGISTRY: Dict[str, "Patch"] = {}


def get_patch(patch_id: str) -> "Patch":
    if patch_id not in REGISTRY:
        raise KeyError(f"unknown patch: {patch_id!r}")
    return REGISTRY[patch_id]


def registered_ids() -> tuple:
    return tuple(REGISTRY.keys())
