"""Provider detail text helpers for setup creation."""

from ..variants import CCR_OAUTH_PROVIDER_KEY
from .options_variant_provider import _default_provider_section, _highlighted_variant_provider, _string_list
from .options_variant_state import _provider_model_discovery_enabled

__all__ = [
    "variant_provider_detail_lines",
    "_provider_model_proxy_lines",
    "variant_model_proxy_supported",
    "_list_or_none",
    "_provider_model_lines",
]

def variant_provider_detail_lines(state):
    provider = _highlighted_variant_provider(state)
    if provider is None:
        return ["No provider selected."]

    tui = provider.get("tui") or {}
    headline = str(tui.get("headline") or provider.get("label") or provider.get("key") or "Provider")
    description = str(provider.get("description") or "No description.")
    lines = [
        headline,
        "",
        description,
        "",
        "Configuration",
        f"Provider key: {provider.get('key') or '?'}",
        f"Section: {provider.get('section') or _default_provider_section(provider.get('key'))}",
        f"Auth: {provider.get('authMode') or 'apiKey'}",
        f"Credential env: {provider.get('credentialEnv') or 'not required'}",
        f"Endpoint: {provider.get('baseUrl') or 'provider default'}",
        f"Model mapping: {'required' if provider.get('requiresModelMapping') else 'provider defaults'}",
        f"Model discovery: {'enabled' if _provider_model_discovery_enabled(provider) else 'not available'}",
        "",
        "Enabled by default",
        f"Prompt pack: {'off' if provider.get('noPromptPack') else 'on'}",
        f"MCP servers: {_list_or_none(provider.get('mcpServers'))}",
        f"Settings deny: {_list_or_none(provider.get('settingsPermissionsDeny'))}",
        f"Env unset: {_list_or_none(provider.get('envUnset'))}",
    ]

    model_lines = _provider_model_lines(provider)
    if model_lines:
        lines.extend(["", "Models", *model_lines])

    features = _string_list(tui.get("features"))
    if features:
        lines.extend(["", "Features", *[f"- {feature}" for feature in features]])

    model_proxy_lines = _provider_model_proxy_lines(provider)
    if model_proxy_lines:
        lines.extend(["", "OAuth architect proxy", *model_proxy_lines])

    setup_note = str(tui.get("setupNote") or "").strip()
    if setup_note:
        lines.extend(["", "Setup note", setup_note])

    links = tui.get("setupLinks") or {}
    if isinstance(links, dict) and links:
        lines.extend(["", "Setup links"])
        for key, value in sorted(links.items()):
            lines.append(f"{key}: {value}")

    return lines

def _provider_model_proxy_lines(provider):
    if not variant_model_proxy_supported(provider):
        return []
    lines = [
        "- Wizard: enable OAuth architect proxy on the Tweaks step",
        "- Requires Claude Code account/login; claude-* calls use OAuth/session",
        "- Non-Claude worker aliases route to this provider backend",
        "- Sets CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1; disabling that tweak disables the proxy",
    ]
    if provider.get("key") == CCR_OAUTH_PROVIDER_KEY:
        lines.append("- Managed CCR is started setup-locally before the proxy starts")
    return lines

def variant_model_proxy_supported(provider):
    if not provider:
        return False
    if provider.get("authMode") not in {"apiKey", "authToken"}:
        return False
    section = str(provider.get("section") or _default_provider_section(provider.get("key")))
    return section == "cloud" or provider.get("key") == CCR_OAUTH_PROVIDER_KEY

def _list_or_none(values):
    values = [str(value) for value in (values or []) if str(value)]
    return ", ".join(values) if values else "none"

def _provider_model_lines(provider):
    models = provider.get("models") or {}
    if not isinstance(models, dict) or not models:
        return []
    return [
        f"{key}: {value}"
        for key, value in sorted(models.items())
        if str(value).strip()
    ]
