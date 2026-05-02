"""Backwards-compatible shim for the legacy ``cc_extractor.variant_tweaks``
import path. The implementation lives in :mod:`cc_extractor.variants.tweaks`.
"""

from .variants.tweaks import (  # noqa: F401
    CURATED_TWEAK_IDS,
    DASHBOARD_EXCLUDED_TWEAK_IDS,
    DASHBOARD_TWEAK_IDS,
    CUSTOM_MODELS,
    DEFAULT_TWEAK_IDS,
    ENV_TWEAK_IDS,
    TweakPatchError,
    TweakResult,
    apply_variant_tweaks,
    available_tweaks,
    env_for_tweaks,
    normalize_tweak_ids,
)
