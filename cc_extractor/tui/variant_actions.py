"""Variant-tab action helpers (no monkey-patched dependencies)."""

from ..providers import provider_default_variant_name
from ..variant_tweaks import CURATED_TWEAK_IDS, DEFAULT_TWEAK_IDS
from ._const import VARIANT_MODEL_FIELDS, VARIANT_STEPS
from .options import (
    selected_variant_provider,
    variant_model_display_value,
)


def advance_variant(state):
    state.variant_step = min(state.variant_step + 1, len(VARIANT_STEPS) - 1)
    state.selected_index = 0


def reset_variant(state):
    state.variant_step = 0
    state.selected_index = 0
    state.variant_name = ""
    state.variant_credential_env = ""
    state.variant_model_overrides = {}
    state.selected_variant_tweaks = list(DEFAULT_TWEAK_IDS)


def set_variant_provider_defaults(state, provider):
    state.variant_name = provider_default_variant_name(provider["key"]) if provider else ""
    state.variant_credential_env = str(provider.get("credentialEnv") or "") if provider else ""
    state.variant_model_overrides = {}


def toggle_variant_tweak(state, tweak_id: str):
    if tweak_id in state.selected_variant_tweaks:
        state.selected_variant_tweaks.remove(tweak_id)
    else:
        state.selected_variant_tweaks.append(tweak_id)
        state.selected_variant_tweaks.sort(key=lambda item: CURATED_TWEAK_IDS.index(item))


def require_variant_model_mapping(state) -> bool:
    provider = selected_variant_provider(state)
    if not provider or not provider.get("requiresModelMapping"):
        return True
    missing = [
        label
        for key, label in VARIANT_MODEL_FIELDS[:3]
        if not variant_model_display_value(state, provider, key)
    ]
    if missing:
        state.message = f"Set model aliases for: {', '.join(missing)}"
        return False
    return True


def variant_credential_env_for_create(state, provider):
    value = state.variant_credential_env.strip()
    if not value:
        return None
    if (
        provider.get("credentialOptional")
        and value == provider.get("credentialEnv")
        and provider.get("authTokenFallback")
    ):
        return None
    if provider.get("authMode") == "none":
        return None
    return value


def variant_model_overrides_for_create(state):
    return {
        key: value.strip()
        for key, value in state.variant_model_overrides.items()
        if value.strip()
    }
