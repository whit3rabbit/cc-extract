"""Shared state helpers for setup creation options."""

__all__ = [
    "_provider_model_discovery_enabled",
    "variant_model_display_value",
    "selected_variant_provider",
]

def _provider_model_discovery_enabled(provider):
    discovery = (provider or {}).get("modelDiscovery") or {}
    return bool(discovery.get("enabled"))

def variant_model_display_value(state, provider, key):
    override = state.variant_model_overrides.get(key, "").strip()
    if override:
        return override
    if not provider:
        return ""
    return str(provider.get("models", {}).get(key) or "")

def selected_variant_provider(state):
    if not state.variant_providers:
        return None
    index = max(0, min(state.variant_provider_index, len(state.variant_providers) - 1))
    return state.variant_providers[index]
