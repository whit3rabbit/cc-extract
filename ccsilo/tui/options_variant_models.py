"""Model editor option helpers for setup variants."""

from ._const import MenuOption, VARIANT_MODEL_FIELDS
from .options_variant_state import _provider_model_discovery_enabled

__all__ = [
    "provider_for_setup",
    "models_edit_options",
    "models_edit_variant",
    "selected_models_edit_option",
    "models_display_value",
    "models_pending_diff",
    "_models_choice_selected",
]

def provider_for_setup(state, variant):
    provider_key = str(((variant.manifest or {}).get("provider") or {}).get("key") or "")
    for provider in state.variant_providers:
        if provider.get("key") == provider_key:
            return provider
    return {
        "key": provider_key,
        "label": provider_key or "?",
        "models": {},
        "modelDiscovery": {},
        "requiresModelMapping": bool((variant.manifest or {}).get("modelOverrides")),
    }

def models_edit_options(state):
    variant = models_edit_variant(state)
    if variant is None:
        return [MenuOption("models-back", "Back to setup")]
    provider = provider_for_setup(state, variant)
    options = []
    if _provider_model_discovery_enabled(provider):
        options.append(MenuOption("models-refresh", "Refresh model list"))
        if state.models_choices:
            for model_id in state.models_choices:
                marker = "*" if _models_choice_selected(state, model_id) else " "
                options.append(MenuOption("models-choice", f"{marker} {model_id}", model_id))
        else:
            options.append(MenuOption("section", "No models loaded"))
    for key, label in VARIANT_MODEL_FIELDS:
        value = models_display_value(state, provider, key)
        source = "override" if state.models_pending.get(key, "").strip() else "default"
        options.append(MenuOption("models-field", f"{label}: {value or '(not set)'} ({source})", key))
    options.append(MenuOption("models-apply", "Apply model changes"))
    options.append(MenuOption("models-discard", "Discard model changes"))
    return options

def models_edit_variant(state):
    if not state.models_variant_id:
        return None
    for variant in state.variants:
        if variant.variant_id == state.models_variant_id:
            return variant
    return None

def selected_models_edit_option(state):
    options = models_edit_options(state)
    if not options:
        return None
    index = max(0, min(state.selected_index, len(options) - 1))
    return options[index]

def models_display_value(state, provider, key):
    override = state.models_pending.get(key, "").strip()
    if override:
        return override
    return str((provider or {}).get("models", {}).get(key) or "")

def models_pending_diff(state):
    baseline = {
        key: value
        for key, value in (state.models_baseline or {}).items()
        if str(value or "").strip()
    }
    pending = {
        key: value
        for key, value in (state.models_pending or {}).items()
        if str(value or "").strip()
    }
    return {
        "changed": sorted(key for key in set(baseline) | set(pending) if baseline.get(key) != pending.get(key)),
        "pending": pending,
    }

def _models_choice_selected(state, model_id):
    pending = state.models_pending or {}
    return bool(pending) and all(pending.get(key) == model_id for key, _label in VARIANT_MODEL_FIELDS)
