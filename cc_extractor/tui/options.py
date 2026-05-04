"""Option generators, summary builders, and selection helpers.

These functions are pure: they read state and return data structures (lists of
MenuOption, label strings, lookup helpers). They do not mutate state and do not
call any externally-monkey-patched function.
"""

from pathlib import Path
from types import SimpleNamespace

from .._utils import version_sort_key
from ..patches._registry import REGISTRY as PATCH_REGISTRY, patches_grouped
from ..patches._versions import SemverRangeError, version_in_range
from ..providers import PLUGIN_RECOMMENDATIONS, list_optional_mcp_entries
from ..variant_tweaks import (
    CURATED_TWEAK_IDS,
    DASHBOARD_TWEAK_IDS,
    DEFAULT_TWEAK_IDS,
    ENV_TWEAK_IDS,
    PROMPT_ONLY_TWEAK_IDS,
)
from ..workspace import short_sha
from ._const import (
    DASHBOARD_STEPS,
    MenuOption,
    SOURCE_ARTIFACT,
    SOURCE_LATEST,
    SOURCE_VERSION,
    VARIANT_MODEL_FIELDS,
    VARIANT_STEPS,
)

ENV_TWEAK_META = {
    "context-limit": (
        "Context limit",
        "environment",
        "Sets CLAUDE_CODE_CONTEXT_LIMIT and disables automatic compaction.",
    ),
    "file-read-limit": (
        "File read limit",
        "environment",
        "Sets CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS.",
    ),
    "subagent-model": (
        "Subagent model",
        "environment",
        "Sets CLAUDE_CODE_SUBAGENT_MODEL.",
    ),
}
PROMPT_ONLY_TWEAK_META = {
    "rtk-shell-prefix": (
        "RTK shell prefix",
        "prompts",
        "Adds setup prompt guidance to prefix shell commands with rtk when available.",
    ),
}


# -- Dashboard options --------------------------------------------------------

def dashboard_options(state):
    if state.dashboard_step == 0:
        return _dashboard_source_options(state)
    if state.dashboard_step == 1:
        return _dashboard_patch_options(state)
    if state.dashboard_step == 2:
        return _dashboard_profile_options(state)
    return _dashboard_review_options(state)


def _dashboard_source_options(state):
    options = [
        MenuOption("source-latest", _selected_label(state, SOURCE_LATEST, None, "Latest native binary")),
        MenuOption("refresh-index", "Refresh version list"),
    ]
    latest = state.download_index.get("binary", {}).get("latest")
    for version in state.download_versions:
        suffix = " (latest)" if version == latest else ""
        label = f"Native {version}{suffix}"
        options.append(MenuOption("source-version", _selected_label(state, SOURCE_VERSION, version, label), version))
    if state.native_artifacts:
        options.append(MenuOption("section", "Downloaded native artifacts"))
    for index, artifact in enumerate(state.native_artifacts):
        label = f"Downloaded {format_native_artifact(artifact)}"
        options.append(MenuOption("source-artifact", _selected_label(state, SOURCE_ARTIFACT, index, label), index))
    return options


def _dashboard_patch_options(state):
    options = []
    for tweak_id in dashboard_tweak_ids():
        patch = PATCH_REGISTRY[tweak_id]
        marker = "[x]" if tweak_id in state.selected_dashboard_tweak_ids else "[ ]"
        options.append(MenuOption("dashboard-tweak-toggle", f"{marker} {patch.id}  {patch.name}", tweak_id))

    if state.dashboard_tweak_profiles:
        options.append(MenuOption("section", "Saved profiles"))
    for profile in state.dashboard_tweak_profiles:
        missing = dashboard_tweak_profile_missing_ids(state, profile)
        if missing:
            label = f"Load profile: {profile.name} (invalid, missing {', '.join(missing)})"
        else:
            label = f"Load profile: {profile.name} ({len(profile.tweak_ids)} tweaks)"
        options.append(MenuOption("profile-load", label, profile.profile_id))

    if selected_dashboard_tweaks(state):
        options.append(MenuOption("patch-continue", "Continue to profile management"))
    return options


def _dashboard_profile_options(state):
    name = state.dashboard_profile_name or "(type a profile name)"
    options = [
        MenuOption("profile-name", f"Name: {name}"),
        MenuOption("profile-create", "Create new profile from selected tweaks"),
        MenuOption("review-continue", "Continue to review"),
    ]
    for profile in state.dashboard_tweak_profiles:
        suffix = " [loaded]" if profile.profile_id == state.dashboard_loaded_profile_id else ""
        options.extend([
            MenuOption("profile-load", f"Load profile: {profile.name}{suffix}", profile.profile_id),
            MenuOption("profile-rename", f"Rename profile to typed name: {profile.name}", profile.profile_id),
            MenuOption("profile-overwrite", f"Overwrite profile with selected tweaks: {profile.name}", profile.profile_id),
            MenuOption("profile-delete", _delete_label(state, profile), profile.profile_id),
        ])
    return options


def _dashboard_review_options(state):
    return [
        MenuOption("review-run", "Run dashboard build"),
        MenuOption("review-back", "Back to profile management"),
        MenuOption("review-reset", "Reset dashboard wizard"),
    ]


def _selected_label(state, kind, value, label):
    selected = False
    if state.dashboard_source_kind == kind:
        if kind == SOURCE_LATEST:
            selected = True
        elif kind == SOURCE_VERSION:
            selected = state.dashboard_source_version == value
        elif kind == SOURCE_ARTIFACT:
            selected = state.dashboard_source_artifact_index == value
    return f"* {label}" if selected else f"  {label}"


def _delete_label(state, profile):
    if state.dashboard_delete_confirm_id == profile.profile_id:
        return f"Confirm delete profile: {profile.name}"
    return f"Delete profile: {profile.name}"


# -- Variant options ----------------------------------------------------------

def setup_manager_options(state):
    options = [MenuOption("setup-action-new", "Create new setup")]
    for variant in setup_manager_variants(state):
        options.append(MenuOption("setup-row", setup_row_label(state, variant), variant.variant_id))
    return options


def setup_provider_keys(state):
    return sorted({
        str((variant.manifest.get("provider") or {}).get("key") or "?")
        for variant in state.variants
        if variant.manifest
    })


def setup_manager_variants(state):
    variants = list(state.variants)
    provider_filter = getattr(state, "setup_provider_filter", "all") or "all"
    if provider_filter != "all":
        variants = [
            variant for variant in variants
            if _setup_provider(variant) == provider_filter
        ]

    query = (getattr(state, "setup_search_text", "") or "").strip().lower()
    if query:
        variants = [
            variant for variant in variants
            if query in _setup_search_text(variant)
        ]

    return sorted(variants, key=lambda variant: _setup_sort_value(state, variant))


def setup_manager_empty_label(state):
    if not state.variants:
        return "No setups found."
    if len(setup_manager_variants(state)) == 0:
        return "No setups match current search/filter."
    return ""


def setup_manager_control_summary(state):
    search = getattr(state, "setup_search_text", "") or ""
    search_label = search if search else "none"
    if getattr(state, "setup_search_active", False):
        search_label = f"{search_label} (typing)"
    provider = getattr(state, "setup_provider_filter", "all") or "all"
    sort_key = getattr(state, "setup_sort_key", "name") or "name"
    return f"Search: {search_label} | Provider: {provider} | Sort: {sort_key}"


def _setup_sort_value(state, variant):
    sort_key = getattr(state, "setup_sort_key", "name") or "name"
    if sort_key == "provider":
        return (_setup_provider(variant), variant.variant_id)
    if sort_key == "health":
        return (_setup_health_rank(setup_health_status(state, variant.variant_id)), variant.variant_id)
    if sort_key == "updated":
        return (_setup_updated(variant), variant.variant_id)
    if sort_key == "version":
        return (version_sort_key(_setup_version(variant)), variant.variant_id)
    return (variant.variant_id, )


def _setup_search_text(variant):
    manifest = variant.manifest or {}
    paths = manifest.get("paths") or {}
    wrapper = str(paths.get("wrapper") or "")
    parts = [
        variant.variant_id,
        str(manifest.get("name") or ""),
        _setup_provider(variant),
        _setup_version(variant),
        wrapper,
        Path(wrapper).name if wrapper else "",
    ]
    return " ".join(parts).lower()


def _setup_provider(variant):
    manifest = variant.manifest or {}
    return str((manifest.get("provider") or {}).get("key") or "?")


def _setup_version(variant):
    manifest = variant.manifest or {}
    return str((manifest.get("source") or {}).get("version") or "?")


def _setup_updated(variant):
    manifest = variant.manifest or {}
    return str(manifest.get("updatedAt") or "")


def _setup_health_rank(status):
    return {
        "broken": 0,
        "warning": 1,
        "unknown": 2,
        "never": 3,
        "healthy": 4,
    }.get(str(status), 2)


def setup_detail_options(state):
    setup_id = selected_setup_id(state)
    if setup_id is None:
        return [MenuOption("setup-action-new", "Create new setup")]
    return [
        MenuOption("setup-action-run", "Run Claude", setup_id),
        MenuOption("setup-action-health", "Run health check", setup_id),
        MenuOption("setup-action-upgrade", "Upgrade Claude Code", setup_id),
        MenuOption("setup-action-tweaks", "Edit tweaks", setup_id),
        MenuOption("setup-action-delete", "Delete setup", setup_id),
        MenuOption("setup-action-new", "Create new setup"),
    ]


def setup_row_label(state, variant):
    manifest = variant.manifest or {}
    provider = (manifest.get("provider") or {}).get("key") or "?"
    version = (manifest.get("source") or {}).get("version") or "?"
    health = setup_health_status(state, variant.variant_id)
    return f"{variant.variant_id:<20} {provider:<12} {version:<12} {health:<8} {setup_command_label(variant)}"


def setup_command_label(variant):
    wrapper = (variant.manifest.get("paths") or {}).get("wrapper") if variant.manifest else ""
    if not wrapper:
        return "(no command)"
    return Path(str(wrapper)).name or str(wrapper)


def setup_health_status(state, setup_id):
    summary = state.setup_health.get(setup_id)
    if not summary:
        return "never"
    return str(summary.get("status") or "unknown")


def selected_setup_option(state):
    options = setup_detail_options(state) if state.mode == "setup-detail" else setup_manager_options(state)
    if not options:
        return None
    index = max(0, min(state.selected_index, len(options) - 1))
    return options[index]


def selected_setup_id(state):
    if state.selected_setup_id:
        return state.selected_setup_id
    if state.variants:
        return state.variants[0].variant_id
    return None


def selected_setup_variant(state):
    setup_id = selected_setup_id(state)
    if setup_id is None:
        return None
    for variant in state.variants:
        if variant.variant_id == setup_id:
            return variant
    return None


def setup_detail_lines(state):
    variant = selected_setup_variant(state)
    if variant is None:
        return ["No setup selected."]
    manifest = variant.manifest or {}
    paths = manifest.get("paths") or {}
    provider = (manifest.get("provider") or {}).get("key") or "?"
    version = (manifest.get("source") or {}).get("version") or "?"
    tweak_count = len(manifest.get("tweaks", []) or [])
    return [
        f"Setup: {variant.variant_id}",
        f"Provider: {provider}",
        f"Claude Code: {version}",
        f"Health: {setup_health_status(state, variant.variant_id)}",
        f"Command: {paths.get('wrapper') or '(no command)'}",
        f"Setup config: {variant.path / 'variant.json'}",
        f"Enabled tweaks: {tweak_count}",
    ]


def variant_options(state):
    if state.variant_step == 0:
        options = []
        if state.variants and state.mode not in {"variants", "first-run-setup"}:
            options.append(MenuOption("section", "Existing setups"))
            for variant in state.variants:
                paths = variant.manifest.get("paths", {})
                options.append(MenuOption(
                    "variant-status",
                    f"{variant.variant_id}: {paths.get('wrapper', '(no command)')}",
                    variant.variant_id,
                ))
        if state.variant_providers and state.mode not in {"variants", "first-run-setup"}:
            options.append(MenuOption("section", "Create setup provider"))
        options.extend(_variant_provider_options(state))
        return options
    if state.variant_step == 1:
        name = state.variant_name or "(type a setup name)"
        return [
            MenuOption("variant-name", f"Name: {name}"),
            MenuOption("variant-name-continue", "Continue to credentials"),
        ]
    if state.variant_step == 2:
        provider = selected_variant_provider(state)
        if provider is None:
            credential = state.variant_credential_env or "(none)"
            return [
                MenuOption("variant-credential-env", f"Credential env: {credential}"),
                MenuOption("variant-credentials-continue", "Continue to models"),
            ]
        if provider.get("authMode") == "none":
            return [
                MenuOption("section", "Credentials: not required"),
                MenuOption("variant-credentials-continue", "Continue to models"),
            ]
        endpoint = state.variant_base_url or str(provider.get("baseUrl") or "")
        credential = state.variant_credential_env or "(none)"
        store_marker = "[x]" if state.variant_store_secret else "[ ]"
        options = [
            MenuOption("variant-endpoint", f"Endpoint: {endpoint or '(set endpoint)'}"),
            MenuOption("variant-credential-env", f"Credential env: {credential}"),
            MenuOption("variant-store-secret", f"{store_marker} Store API key locally"),
        ]
        if state.variant_store_secret:
            options.append(MenuOption("variant-api-key", f"API key: {_masked_secret(state.variant_api_key)}"))
        options.append(MenuOption("variant-credentials-continue", "Continue to models"))
        return options
    if state.variant_step == 3:
        provider = selected_variant_provider(state)
        options = []
        provider_mcp = list(provider.get("mcpServers") or []) if provider else []
        if provider_mcp:
            credential_env = str(provider.get("credentialEnv") or "").strip() if provider else ""
            env_note = f" env:{credential_env}" if credential_env else ""
            for name in provider_mcp:
                options.append(
                    MenuOption(
                        "variant-mcp-auto",
                        f"[x] {name}  auto-enabled for this provider{env_note}",
                        name,
                    )
                )
        else:
            options.append(MenuOption("section", "Provider MCP servers: none"))
        for entry in list_optional_mcp_entries():
            marker = "[x]" if entry.id in state.selected_variant_mcp_ids else "[ ]"
            env = ", ".join(entry.required_env)
            auth = f" env:{env}" if env else (" oauth" if entry.auth == "oauth" else "")
            options.append(MenuOption("variant-mcp", f"{marker} {entry.name}  ({entry.id}){auth}", entry.id))
        options.append(MenuOption("section", f"Plugin recommendations: {', '.join(PLUGIN_RECOMMENDATIONS)}"))
        next_label = "Continue to models" if provider and provider.get("requiresModelMapping") else "Continue to tweaks"
        options.append(MenuOption("variant-mcp-continue", next_label))
        return options
    if state.variant_step == 4:
        provider = selected_variant_provider(state)
        if provider and not provider.get("requiresModelMapping"):
            return [
                MenuOption("variant-models-default", "Using provider default models"),
                MenuOption("variant-models-continue", "Continue to tweaks"),
            ]
        options = []
        if _provider_model_discovery_enabled(provider):
            options.append(MenuOption("variant-model-refresh", "Refresh model list"))
            if state.variant_model_choices:
                for model_id in state.variant_model_choices:
                    selected = _model_choice_selected(state, model_id)
                    marker = "*" if selected else " "
                    options.append(MenuOption("variant-model-choice", f"{marker} {model_id}", model_id))
            else:
                options.append(MenuOption("section", "No models loaded"))
        for key, label in VARIANT_MODEL_FIELDS:
            value = variant_model_display_value(state, provider, key)
            source = "override" if state.variant_model_overrides.get(key, "").strip() else "default"
            options.append(MenuOption("variant-model", f"{label}: {value or '(not set)'} ({source})", key))
        options.append(MenuOption("variant-models-continue", "Continue to tweaks"))
        return options
    if state.variant_step == 5:
        options = []
        tweak_ids = list(DEFAULT_TWEAK_IDS) if state.tweak_filter == "recommended" else list(CURATED_TWEAK_IDS)
        for tweak_id in tweak_ids:
            marker = "[x]" if tweak_id in state.selected_variant_tweaks else "[ ]"
            options.append(MenuOption("variant-tweak", f"{marker} {_tweak_display_name(tweak_id)}  ({tweak_id})", tweak_id))
        if state.tweak_filter == "recommended":
            options.append(MenuOption("variant-tweak-view", "Show advanced tweaks", "all"))
        else:
            options.append(MenuOption("variant-tweak-view", "Show recommended tweaks", "recommended"))
        options.append(MenuOption("variant-tweaks-continue", "Continue to review"))
        return options
    return [
        MenuOption("variant-create", "Preview setup create"),
        MenuOption("variant-review-back", "Back to tweaks"),
        MenuOption("variant-reset", "Reset setup wizard"),
    ]


def _variant_provider_options(state):
    options = []
    for provider in _providers_for_section(state, "pinned"):
        options.append(_variant_provider_option(state, provider))
    cloud = _providers_for_section(state, "cloud")
    if cloud:
        options.append(MenuOption("section", "Cloud Providers"))
        options.extend(_variant_provider_option(state, provider) for provider in cloud)
    local = _providers_for_section(state, "local")
    if local:
        options.append(MenuOption("section", "Local LLMs"))
        options.extend(_variant_provider_option(state, provider) for provider in local)
    return options


def _providers_for_section(state, section):
    providers = [
        (index, provider)
        for index, provider in enumerate(state.variant_providers)
        if str(provider.get("section") or _default_provider_section(provider.get("key"))) == section
    ]
    if section == "pinned":
        order = {"mirror": 0, "ccrouter": 1}
        providers.sort(key=lambda item: (order.get(item[1].get("key"), 99), item[1].get("label", "")))
    return providers


def _default_provider_section(provider_key):
    if provider_key in {"mirror", "ccrouter"}:
        return "pinned"
    if provider_key in {"ollama", "lmstudio", "omlx", "local-custom"}:
        return "local"
    return "cloud"


def _variant_provider_option(state, item):
    index, provider = item
    return MenuOption(
        "variant-provider",
        f"{provider['key']}  {provider['label']} - {provider.get('description', '')} {_provider_markers(provider)}",
        index,
    )


def variant_provider_selector_labels(state):
    labels = []
    for option in variant_options(state):
        if option.kind == "variant-provider":
            labels.append(_variant_provider_row_label(_provider_by_index(state, option.value)))
        else:
            labels.append(option.label)
    return labels


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

    setup_note = str(tui.get("setupNote") or "").strip()
    if setup_note:
        lines.extend(["", "Setup note", setup_note])

    links = tui.get("setupLinks") or {}
    if isinstance(links, dict) and links:
        lines.extend(["", "Setup links"])
        for key, value in sorted(links.items()):
            lines.append(f"{key}: {value}")

    return lines


def _variant_provider_row_label(provider):
    if not provider:
        return "unknown provider"
    key = str(provider.get("key") or "?")
    label = str(provider.get("label") or key)
    markers = []
    auth_mode = provider.get("authMode") or "apiKey"
    if auth_mode == "none":
        markers.append("no-auth")
    else:
        markers.append(str(auth_mode))
    if provider.get("requiresModelMapping"):
        markers.append("model-map")
    if provider.get("mcpServers"):
        markers.append("mcp")
    if provider.get("section") == "local" or provider.get("baseUrl", "").startswith(("http://127.0.0.1", "http://localhost")):
        markers.append("local")
    return f"{key}  {label} [{', '.join(markers)}]"


def _highlighted_variant_provider(state):
    option = selected_variant_option(state)
    if option is not None and option.kind == "variant-provider":
        return _provider_by_index(state, option.value)
    return selected_variant_provider(state)


def _provider_by_index(state, value):
    try:
        index = int(value)
    except (TypeError, ValueError):
        return None
    if index < 0 or index >= len(state.variant_providers):
        return None
    return state.variant_providers[index]


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


def _string_list(value):
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _masked_secret(value):
    return "set" if str(value or "").strip() else "not set"


def _provider_model_discovery_enabled(provider):
    discovery = (provider or {}).get("modelDiscovery") or {}
    return bool(discovery.get("enabled"))


def _model_choice_selected(state, model_id):
    overrides = state.variant_model_overrides or {}
    return bool(overrides) and all(overrides.get(key) == model_id for key, _label in VARIANT_MODEL_FIELDS)


def _provider_markers(provider):
    markers = []
    auth_mode = provider.get("authMode") or "apiKey"
    markers.append(f"auth:{auth_mode}")
    if provider.get("credentialOptional"):
        markers.append("credential:optional")
    if provider.get("requiresModelMapping"):
        markers.append("model-map:required")
    if provider.get("section") == "local" or provider.get("baseUrl", "").startswith(("http://127.0.0.1", "http://localhost")):
        markers.append("local")
    if _provider_model_discovery_enabled(provider):
        markers.append("models:refresh")
    markers.append("prompt-pack:off" if provider.get("noPromptPack") else "prompt-pack:on")
    if provider.get("mcpServers"):
        markers.append("mcp")
    return "[" + ", ".join(markers) + "]"


def variant_model_display_value(state, provider, key):
    override = state.variant_model_overrides.get(key, "").strip()
    if override:
        return override
    if not provider:
        return ""
    return str(provider.get("models", {}).get(key) or "")


def _tweak_display_name(tweak_id):
    patch = PATCH_REGISTRY.get(tweak_id)
    if patch is not None:
        return patch.name
    if tweak_id in ENV_TWEAK_META:
        return ENV_TWEAK_META[tweak_id][0]
    if tweak_id in PROMPT_ONLY_TWEAK_META:
        return PROMPT_ONLY_TWEAK_META[tweak_id][0]
    return tweak_id.replace("-", " ").title()


# -- Selection helpers --------------------------------------------------------

def selected_dashboard_option(state):
    options = dashboard_options(state)
    if not options:
        return None
    index = max(0, min(state.selected_index, len(options) - 1))
    return options[index]


def selected_variant_option(state):
    options = variant_options(state)
    if not options:
        return None
    index = max(0, min(state.selected_index, len(options) - 1))
    return options[index]


def selected_variant_provider(state):
    if not state.variant_providers:
        return None
    index = max(0, min(state.variant_provider_index, len(state.variant_providers) - 1))
    return state.variant_providers[index]


def dashboard_source_artifact(state):
    if not state.native_artifacts:
        return None
    index = max(0, min(state.dashboard_source_artifact_index, len(state.native_artifacts) - 1))
    return state.native_artifacts[index]


# -- Profile / package helpers ------------------------------------------------

def profile_refs_by_key(state):
    return {
        (package.patch_id, package.version): index
        for index, package in enumerate(state.patch_packages)
    }


def profile_missing_refs(state, profile):
    available = profile_refs_by_key(state)
    missing = []
    for ref in profile.patches:
        key = (ref["id"], ref["version"])
        if key not in available:
            missing.append(f"{ref['id']}@{ref['version']}")
    return missing


def profile_by_id(state, profile_id):
    for profile in state.patch_profiles:
        if profile.profile_id == profile_id:
            return profile
    return None


def dashboard_tweak_profile_by_id(state, profile_id):
    for profile in state.dashboard_tweak_profiles:
        if profile.profile_id == profile_id:
            return profile
    return None


def loaded_profile(state):
    if not state.dashboard_loaded_profile_id:
        return None
    profile = dashboard_tweak_profile_by_id(state, state.dashboard_loaded_profile_id)
    if profile is not None:
        return profile
    return profile_by_id(state, state.dashboard_loaded_profile_id)


def dashboard_tweak_ids():
    return [tweak_id for tweak_id in DASHBOARD_TWEAK_IDS if tweak_id in PATCH_REGISTRY]


def dashboard_tweak_profile_missing_ids(state, profile):
    if not hasattr(profile, "tweak_ids"):
        return [f"{profile.profile_id} is not a dashboard tweak profile"]
    available = set(dashboard_tweak_ids())
    return [tweak_id for tweak_id in profile.tweak_ids if tweak_id not in available]


def selected_dashboard_tweaks(state):
    available = set(dashboard_tweak_ids())
    return [
        tweak_id for tweak_id in state.selected_dashboard_tweak_ids
        if tweak_id in available
    ]


def selected_dashboard_packages(state):
    return [
        state.patch_packages[index]
        for index in state.selected_patch_indexes
        if 0 <= index < len(state.patch_packages)
    ]


def selected_patch_refs(state):
    return [
        {"id": package.patch_id, "version": package.version}
        for package in selected_dashboard_packages(state)
    ]


# -- Summaries ----------------------------------------------------------------

def dashboard_title(state):
    return f"Dashboard: {DASHBOARD_STEPS[state.dashboard_step]}"


def dashboard_steps(state):
    labels = []
    for index, step in enumerate(DASHBOARD_STEPS):
        if index == state.dashboard_step:
            labels.append(f"[{step}]")
        elif index < state.dashboard_step:
            labels.append(f"{step}*")
        else:
            labels.append(step)
    return "Steps: " + " > ".join(labels)


def dashboard_summary(state):
    profile = loaded_profile(state)
    profile_label = profile.name if profile else "none"
    return (
        f"Source: {dashboard_source_label(state)}  "
        f"Patches: {len(selected_dashboard_tweaks(state))}  "
        f"Profile: {profile_label}"
    )


def dashboard_source_label(state):
    if state.dashboard_source_kind == SOURCE_VERSION:
        return f"native {state.dashboard_source_version}"
    if state.dashboard_source_kind == SOURCE_ARTIFACT:
        artifact = dashboard_source_artifact(state)
        if artifact is None:
            return "downloaded artifact unavailable"
        return f"downloaded {artifact.version} {artifact.platform} {short_sha(artifact.sha256)}"
    return "latest native"


def variant_title(state):
    return f"Create setup: {VARIANT_STEPS[state.variant_step]}"


def variant_steps(state):
    labels = []
    for index, step in enumerate(VARIANT_STEPS):
        if index == state.variant_step:
            labels.append(f"[{step}]")
        elif index < state.variant_step:
            labels.append(f"{step}*")
        else:
            labels.append(step)
    return "Setup steps: " + " > ".join(labels)


def variant_summary(state):
    provider = selected_variant_provider(state)
    name = state.variant_name or (provider.get("defaultVariantName") if provider else "")
    credential = state.variant_credential_env or "none"
    model_count = len([value for value in state.variant_model_overrides.values() if value.strip()])
    return (
        f"Provider: {provider.get('key') if provider else 'none'}  "
        f"Name: {name or 'none'}  "
        f"Credential env: {credential}  "
        f"Model overrides: {model_count}  "
        f"Tweaks: {len(state.selected_variant_tweaks)}"
    )


# -- Tweaks options -----------------------------------------------------------

def tweaks_source_options(state):
    options = []
    if not state.variants:
        options.append(MenuOption("section", "No setups found - create one first"))
        return options
    for variant in state.variants:
        manifest = variant.manifest or {}
        tweak_count = len(manifest.get("tweaks", []) or [])
        provider = (manifest.get("provider") or {}).get("key") or "?"
        version = (manifest.get("source") or {}).get("version") or "?"
        label = f"{variant.variant_id}  ({provider}, claude {version}, {tweak_count} tweaks)"
        options.append(MenuOption("tweaks-pick-variant", label, variant.variant_id))
    return options


def tweaks_edit_options(state):
    """Curated tweaks grouped by category. Each item is a togglable row.

    `selected_index` walks only the togglable rows; group headers are returned
    via `tweaks_edit_groups()` for rendering, not as MenuOption entries.
    """
    options = []
    for group, tweaks in _filtered_patches_grouped(state):
        for tweak in tweaks:
            marker = "[x]" if tweak.id in state.tweaks_pending else "[ ]"
            status = tweak_status(state, tweak.id)
            label = f"{marker} {tweak.name}  ({tweak.id})  {status['label']}"
            options.append(MenuOption("tweak-toggle", label, tweak.id))
    return options


def tweaks_edit_groups(state):
    """Return a list of (group_label, [patch_id, ...]) preserving display order.

    The renderer walks options in order and inserts a group header before the
    first patch belonging to each new group.
    """
    return [(group, [patch.id for patch in patches]) for group, patches in _filtered_patches_grouped(state)]


def selected_tweaks_edit_option(state):
    options = tweaks_edit_options(state)
    if not options:
        return None
    index = max(0, min(state.selected_index, len(options) - 1))
    return options[index]


def selected_tweaks_edit_patch(state):
    """Return the Patch-like object currently selected in tweaks-edit mode, or None."""
    option = selected_tweaks_edit_option(state)
    if option is None:
        return None
    return _tweak_meta(str(option.value))


def tweak_control_summary(state):
    search = getattr(state, "tweak_search", "") or ""
    search_label = search if search else "none"
    if getattr(state, "tweak_search_active", False):
        search_label = f"{search_label} (typing)"
    return f"View: {getattr(state, 'tweak_filter', 'recommended') or 'recommended'} | Search: {search_label}"


def tweaks_edit_empty_label(state):
    if len(tweaks_edit_options(state)) == 0:
        return "No tweaks match current search/filter."
    return ""


def selected_setup_version(state):
    variant = selected_setup_variant(state)
    if variant is None:
        return None
    return ((variant.manifest or {}).get("source") or {}).get("version")


def tweak_status(state, tweak_id):
    if tweak_id in ENV_TWEAK_IDS:
        return {"label": "env-backed", "selectable": True, "reason": "Sets environment only."}
    if tweak_id in PROMPT_ONLY_TWEAK_IDS:
        label = "ready" if tweak_id in DEFAULT_TWEAK_IDS else "advanced"
        return {"label": label, "selectable": True, "reason": "Adds prompt overlay instructions."}
    patch = PATCH_REGISTRY.get(tweak_id)
    if patch is None:
        return {"label": "unknown", "selectable": False, "reason": "Tweak is not registered."}
    version = selected_setup_version(state)
    if not version or version == "latest":
        if patch.id in DEFAULT_TWEAK_IDS:
            return {"label": "ready", "selectable": True, "reason": "Version is not pinned yet."}
        return {"label": "advanced", "selectable": True, "reason": "Version is not pinned yet."}
    if version in patch.versions_blacklisted:
        return {
            "label": "blocked: blacklisted version",
            "selectable": False,
            "reason": f"Claude Code {version} is blacklisted for this tweak.",
        }
    try:
        supported = version_in_range(version, patch.versions_supported)
    except SemverRangeError as exc:
        return {"label": "unsupported", "selectable": False, "reason": str(exc)}
    if not supported:
        return {
            "label": f"unsupported for Claude Code {version}",
            "selectable": False,
            "reason": f"Supported range: {patch.versions_supported}",
        }
    if patch.id in DEFAULT_TWEAK_IDS:
        return {"label": "ready", "selectable": True, "reason": "Recommended setup tweak."}
    return {"label": "advanced", "selectable": True, "reason": "Advanced tweak. Review before enabling."}


def tweak_diff(state):
    pending = set(state.tweaks_pending or [])
    baseline = set(state.tweaks_baseline or ())
    return sorted(pending - baseline), sorted(baseline - pending)


def unsupported_pending_tweaks(state):
    return [
        tweak_id for tweak_id in sorted(set(state.tweaks_pending or []))
        if not tweak_status(state, tweak_id)["selectable"]
    ]


def _filtered_patches_grouped(state):
    grouped = []
    recommended = set(DEFAULT_TWEAK_IDS) | set(state.tweaks_baseline or ()) | set(state.tweaks_pending or [])
    curated = set(CURATED_TWEAK_IDS)
    for group, patches in patches_grouped().items():
        filtered = []
        for patch in patches:
            if patch.id not in curated:
                continue
            if not _tweak_passes_filter(state, patch.id, recommended):
                continue
            filtered.append(patch)
        if filtered:
            grouped.append((group, filtered))
    env_filtered = [
        _tweak_meta(tweak_id)
        for tweak_id in ENV_TWEAK_IDS
        if tweak_id in curated and _tweak_passes_filter(state, tweak_id, recommended)
    ]
    prompt_only_filtered = [
        _tweak_meta(tweak_id)
        for tweak_id in PROMPT_ONLY_TWEAK_IDS
        if tweak_id in curated and _tweak_passes_filter(state, tweak_id, recommended)
    ]
    if prompt_only_filtered:
        for index, (group, patches) in enumerate(grouped):
            if group == "prompts":
                grouped[index] = (group, [*patches, *prompt_only_filtered])
                break
        else:
            grouped.append(("prompts", prompt_only_filtered))
    if env_filtered:
        grouped.append(("environment", env_filtered))
    return grouped


def _tweak_meta(tweak_id):
    patch = PATCH_REGISTRY.get(tweak_id)
    if patch is not None:
        return patch
    if tweak_id in PROMPT_ONLY_TWEAK_META:
        name, group, description = PROMPT_ONLY_TWEAK_META[tweak_id]
        return SimpleNamespace(
            id=tweak_id,
            name=name,
            group=group,
            versions_supported="prompt-only",
            versions_tested=("prompt-only",),
            versions_blacklisted=(),
            on_miss="skip",
            description=description,
        )
    if tweak_id not in ENV_TWEAK_META:
        return None
    name, group, description = ENV_TWEAK_META[tweak_id]
    return SimpleNamespace(
        id=tweak_id,
        name=name,
        group=group,
        versions_supported="env-backed",
        versions_tested=("env-backed",),
        versions_blacklisted=(),
        on_miss="skip",
        description=description,
    )


def _tweak_passes_filter(state, tweak_id, recommended):
    status = tweak_status(state, tweak_id)
    if state.tweak_filter == "recommended" and tweak_id not in recommended:
        return False
    if state.tweak_filter == "advanced" and tweak_id in DEFAULT_TWEAK_IDS:
        return False
    if state.tweak_filter == "incompatible" and status["selectable"]:
        return False
    meta = _tweak_meta(tweak_id)
    if meta is None:
        return False
    search_text = f"{meta.id} {meta.name} {meta.group} {meta.description}".lower()
    if state.tweak_search and state.tweak_search.lower() not in search_text:
        return False
    return True


def selected_tweaks_source_variant_id(state):
    if not state.variants:
        return None
    index = max(0, min(state.selected_index, len(state.variants) - 1))
    return state.variants[index].variant_id


# -- Native artifact formatting -----------------------------------------------

def format_native_artifact(artifact):
    return f"{artifact.version}  {artifact.platform}  {short_sha(artifact.sha256)}  {_format_size(artifact)}  {artifact.path}"


def _format_size(artifact):
    size = getattr(artifact, "size", 0)
    if not size:
        return "unknown"
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"
