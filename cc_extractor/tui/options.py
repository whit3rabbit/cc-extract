"""Option generators, summary builders, and selection helpers.

These functions are pure: they read state and return data structures (lists of
MenuOption, label strings, lookup helpers). They do not mutate state and do not
call any externally-monkey-patched function.
"""

from pathlib import Path

from ..patches._registry import REGISTRY as PATCH_REGISTRY, patches_grouped
from ..patches._versions import SemverRangeError, version_in_range
from ..variant_tweaks import CURATED_TWEAK_IDS, DASHBOARD_TWEAK_IDS, DEFAULT_TWEAK_IDS, ENV_TWEAK_IDS
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
    for variant in state.variants:
        options.append(MenuOption("setup-row", setup_row_label(state, variant), variant.variant_id))
    return options


def setup_detail_options(state):
    setup_id = selected_setup_id(state)
    if setup_id is None:
        return [MenuOption("setup-action-new", "Create new setup")]
    return [
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
        for index, provider in enumerate(state.variant_providers):
            marker = "*" if index == state.variant_provider_index else " "
            options.append(MenuOption(
                "variant-provider",
                f"{marker} {provider['key']}  {provider['label']} - {provider.get('description', '')} {_provider_markers(provider)}",
                index,
            ))
        return options
    if state.variant_step == 1:
        name = state.variant_name or "(type a setup name)"
        return [
            MenuOption("variant-name", f"Name: {name}"),
            MenuOption("variant-name-continue", "Continue to credentials"),
        ]
    if state.variant_step == 2:
        provider = selected_variant_provider(state)
        credential = state.variant_credential_env or "(none)"
        if provider and provider.get("authMode") == "none":
            credential = "(not required)"
        return [
            MenuOption("variant-credential-env", f"Credential env: {credential}"),
            MenuOption("variant-credentials-continue", "Continue to models"),
        ]
    if state.variant_step == 3:
        provider = selected_variant_provider(state)
        if provider and not provider.get("requiresModelMapping"):
            return [
                MenuOption("variant-models-default", "Using provider default models"),
                MenuOption("variant-models-continue", "Continue to tweaks"),
            ]
        options = []
        for key, label in VARIANT_MODEL_FIELDS:
            value = variant_model_display_value(state, provider, key)
            source = "override" if state.variant_model_overrides.get(key, "").strip() else "default"
            options.append(MenuOption("variant-model", f"{label}: {value or '(not set)'} ({source})", key))
        options.append(MenuOption("variant-models-continue", "Continue to tweaks"))
        return options
    if state.variant_step == 4:
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


def _provider_markers(provider):
    markers = []
    auth_mode = provider.get("authMode") or "apiKey"
    markers.append(f"auth:{auth_mode}")
    if provider.get("credentialOptional"):
        markers.append("credential:optional")
    if provider.get("requiresModelMapping"):
        markers.append("model-map:required")
    if provider.get("baseUrl", "").startswith(("http://127.0.0.1", "http://localhost")):
        markers.append("local")
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
    """Patches grouped by category. Each item is a togglable patch row.

    `selected_index` walks only the togglable rows; group headers are returned
    via `tweaks_edit_groups()` for rendering, not as MenuOption entries.
    """
    options = []
    for group, patches in _filtered_patches_grouped(state):
        for patch in patches:
            marker = "[x]" if patch.id in state.tweaks_pending else "[ ]"
            status = tweak_status(state, patch.id)
            label = f"{marker} {patch.name}  ({patch.id})  {status['label']}"
            options.append(MenuOption("tweak-toggle", label, patch.id))
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
    """Return the Patch object currently selected in tweaks-edit mode, or None."""
    option = selected_tweaks_edit_option(state)
    if option is None:
        return None
    return PATCH_REGISTRY.get(option.value)


def selected_setup_version(state):
    variant = selected_setup_variant(state)
    if variant is None:
        return None
    return ((variant.manifest or {}).get("source") or {}).get("version")


def tweak_status(state, tweak_id):
    if tweak_id in ENV_TWEAK_IDS:
        return {"label": "env-backed", "selectable": True, "reason": "Sets environment only."}
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
    for group, patches in patches_grouped().items():
        filtered = []
        for patch in patches:
            status = tweak_status(state, patch.id)
            if state.tweak_filter == "recommended" and patch.id not in recommended:
                continue
            if state.tweak_filter == "advanced" and patch.id in DEFAULT_TWEAK_IDS:
                continue
            if state.tweak_filter == "incompatible" and status["selectable"]:
                continue
            if state.tweak_search and state.tweak_search.lower() not in f"{patch.id} {patch.name}".lower():
                continue
            filtered.append(patch)
        if filtered:
            grouped.append((group, filtered))
    return grouped


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
