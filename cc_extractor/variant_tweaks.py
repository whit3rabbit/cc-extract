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
    MCP_BATCH_SIZE_DEFAULT,
    MCP_BATCH_SIZE_ENV,
    PROMPT_ONLY_TWEAK_IDS,
    RTK_SHELL_PREFIX_TEXT,
    SETUP_ENV_ONLY_TWEAK_IDS,
    TweakPatchError,
    TweakResult,
    apply_variant_tweaks,
    available_tweaks,
    compose_prompt_overlays,
    env_for_tweaks,
    normalize_tweak_ids,
    sync_tweak_env,
)
