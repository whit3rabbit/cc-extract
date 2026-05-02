"""Frame, widget, footer, and text rendering helpers.

These functions are pure: they read the state and return strings or widget
objects. They do not mutate state and do not call externally-monkey-patched
functions.
"""

import os
from typing import Optional

from ..variants.model import default_bin_dir, variant_id_from_name
from ..workspace import workspace_root
from ._const import DASHBOARD_STEPS, TABS, TAB_MODES, VARIANT_MODEL_FIELDS, VARIANT_STEPS
from .options import (
    dashboard_options,
    dashboard_source_label,
    dashboard_title,
    dashboard_tweak_ids,
    format_native_artifact,
    loaded_profile,
    selected_dashboard_packages,
    selected_dashboard_tweaks,
    selected_setup_variant,
    selected_variant_provider,
    selected_tweaks_edit_patch,
    variant_model_display_value,
    setup_detail_lines,
    setup_detail_options,
    setup_manager_control_summary,
    setup_manager_empty_label,
    setup_manager_options,
    tweak_control_summary,
    tweak_diff,
    tweak_status,
    tweaks_edit_empty_label,
    tweaks_edit_groups,
    tweaks_edit_options,
    tweaks_source_options,
    unsupported_pending_tweaks,
    variant_options,
    variant_title,
)
from .themes import active_theme, theme_name


# -- Tab + status bar ---------------------------------------------------------

def active_tab(state):
    if state.mode == "patch-package":
        return "Patch"
    if state.mode in {
        "loading",
        "create-preview",
        "first-run-setup",
        "setup-manager",
        "setup-detail",
        "upgrade-preview",
        "delete-confirm",
        "health-result",
        "logs",
        "help",
        "error",
        "variants",
        "tweaks-source",
        "tweaks-edit",
        "tweak-editor",
    }:
        return "Manage Setup"
    for tab, mode in zip(TABS, TAB_MODES):
        if state.mode == mode:
            return tab
    return "Manage Setup"


def active_tab_index(state):
    return TABS.index(active_tab(state))


def tab_bar(state):
    active = active_tab(state)
    parts = []
    for tab in TABS:
        if tab == active:
            parts.append(f"[{tab}]")
        else:
            parts.append(f" {tab} ")
    return "  ".join(parts)


def compact_tab_bar(state):
    active = active_tab(state)
    return " ".join(f"[{tab}]" if tab == active else tab for tab in TABS)


# -- Body labels and progress -------------------------------------------------

def current_labels(state):
    if state.mode == "loading":
        return "Loading setups", ["Refreshing workspace state..."]
    if state.mode == "setup-manager":
        labels = [
            setup_manager_control_summary(state),
            "Name                 Provider     Claude Code  Health   Command",
        ]
        labels.extend(option.label for option in setup_manager_options(state))
        empty_label = setup_manager_empty_label(state)
        if empty_label:
            labels.append(empty_label)
        return "Setup manager", labels
    if state.mode == "setup-detail":
        labels = setup_detail_lines(state) + ["", "Actions"]
        labels.extend(option.label for option in setup_detail_options(state))
        return f"Manage setup: {state.selected_setup_id or 'none'}", labels
    if state.mode == "first-run-setup":
        title = "No Claude Code setups found"
        return f"{title}: {VARIANT_STEPS[state.variant_step]}", [option.label for option in variant_options(state)]
    if state.mode == "create-preview":
        return "Setup create preview", create_preview_labels(state)
    if state.mode == "upgrade-preview":
        return "Upgrade preview", upgrade_preview_labels(state)
    if state.mode == "delete-confirm":
        return "Delete setup", delete_confirm_labels(state)
    if state.mode == "health-result":
        return "Setup result", state.last_action_summary or ["No result available."]
    if state.mode == "logs":
        return "Logs", state.last_action_log or ["No logs available."]
    if state.mode == "help":
        return "Shortcuts", help_labels()
    if state.mode == "error":
        return "Error", state.last_action_summary or [state.message or "Unknown error."]
    if state.mode == "dashboard":
        return dashboard_title(state), [option.label for option in dashboard_options(state)]
    if state.mode == "inspect":
        return "Inspect", [format_native_artifact(artifact) for artifact in state.native_artifacts]
    if state.mode == "extract":
        return "Extract", [format_native_artifact(artifact) for artifact in state.native_artifacts]
    if state.mode == "patch-source":
        return "Patch source", [format_native_artifact(artifact) for artifact in state.native_artifacts]
    if state.mode == "patch-package":
        labels = []
        for index, package in enumerate(state.patch_packages):
            marker = "[x]" if index in state.selected_patch_indexes else "[ ]"
            labels.append(f"{marker} {package.patch_id}@{package.version}  {package.name}")
        return "Patch bundles", labels
    if state.mode == "variants":
        return variant_title(state), [option.label for option in variant_options(state)]
    if state.mode == "tweaks-source":
        return "Tweaks: pick setup", [option.label for option in tweaks_source_options(state)]
    if state.mode in {"tweaks-edit", "tweak-editor"}:
        if state.tweak_apply_preview:
            return "Tweak rebuild preview", tweak_preview_labels(state)
        labels = [tweak_control_summary(state)]
        labels.extend(_tweaks_edit_labels(state))
        empty_label = tweaks_edit_empty_label(state)
        if empty_label:
            labels.append(empty_label)
        title = f"Edit tweaks: {state.tweaks_variant_id or 'no setup'}"
        return title, labels
    return "Status", []


def create_preview_labels(state):
    provider = selected_variant_provider(state)
    if provider is None:
        return ["No provider selected."]
    name = state.variant_name.strip() or str(provider.get("defaultVariantName") or provider.get("key") or "")
    try:
        setup_id = variant_id_from_name(name)
        command = default_bin_dir() / setup_id
    except Exception as exc:
        setup_id = "(invalid)"
        command = "(unavailable)"
        validation = f"Validation: {exc}"
    else:
        validation = "Validation: ready"

    model_lines = _create_preview_model_lines(state, provider)
    tweak_lines = [f"  {tweak_id}" for tweak_id in state.selected_variant_tweaks] or ["  none"]
    return [
        f"Setup: {name or '(unnamed)'}",
        f"Setup id: {setup_id}",
        f"Provider: {provider.get('key') or '?'}",
        "Claude Code: latest",
        f"Command: {command}",
        f"Credential env: {_create_preview_credential(state, provider)}",
        *model_lines,
        "Default tweaks:",
        *tweak_lines,
        validation,
        "",
        "Proceed? y/N",
    ]


def _create_preview_credential(state, provider):
    if provider.get("authMode") == "none":
        return "not required"
    value = state.variant_credential_env.strip()
    if not value:
        return "not set"
    suffix = "set" if value in os.environ else "missing"
    if provider.get("credentialOptional"):
        suffix = f"optional, {suffix}"
    return f"{value} ({suffix})"


def _create_preview_model_lines(state, provider):
    if not provider.get("requiresModelMapping"):
        return ["Models: provider defaults"]
    lines = ["Models:"]
    for key, label in VARIANT_MODEL_FIELDS:
        value = variant_model_display_value(state, provider, key)
        source = "override" if state.variant_model_overrides.get(key, "").strip() else "default"
        lines.append(f"  {label}: {value or '(not set)'} ({source})")
    return lines


def upgrade_preview_labels(state):
    variant = selected_setup_variant(state)
    if variant is None:
        return ["No setup selected."]
    manifest = variant.manifest or {}
    current = (manifest.get("source") or {}).get("version") or "?"
    target = state.setup_upgrade_target or "latest"
    tweaks = manifest.get("tweaks", []) or []
    paths = manifest.get("paths") or {}
    return [
        f"Setup: {variant.variant_id}",
        f"Current Claude Code: {current}",
        f"Target Claude Code: {target}",
        f"Tweak count: {len(tweaks)}",
        f"Command path: {paths.get('wrapper') or '(no command)'}",
        "Rebuild: yes",
        "",
        "Proceed? y/N",
    ]


def delete_confirm_labels(state):
    variant = selected_setup_variant(state)
    if variant is None:
        return ["No setup selected."]
    paths = (variant.manifest or {}).get("paths") or {}
    return [
        f"Type setup id to delete: {variant.variant_id}",
        f"Typed: {state.delete_confirm_text or '(empty)'}",
        "",
        "Will remove:",
        f"Setup directory: {variant.path}",
        f"Command: {paths.get('wrapper') or '(no command)'}",
        "",
        "Shared downloads and caches are not removed.",
    ]


def help_labels():
    return [
        "Global",
        "Up/Down: move",
        "Enter: select or confirm current screen",
        "Esc/B: back",
        "Q: quit",
        "?: shortcuts",
        "T: cycle theme outside setup manager/detail",
        "",
        "Setup manager",
        "/: search setups",
        "P: cycle provider filter",
        "S: cycle sort",
        "N: new setup",
        "X: run selected setup",
        "U: upgrade selected setup",
        "T: edit tweaks for selected setup",
        "H: run health check",
        "D: delete selected setup",
        "R: refresh setups",
        "",
        "Setup detail and results",
        "C: copy command path",
        "G: copy setup config path",
        "L: view logs",
        "",
        "Logs",
        "C: copy log text",
    ]


def tweak_preview_labels(state):
    variant = selected_setup_variant(state)
    added, removed = tweak_diff(state)
    unsupported = unsupported_pending_tweaks(state)
    command = ""
    if variant is not None:
        command = ((variant.manifest or {}).get("paths") or {}).get("wrapper") or ""
    labels = [
        f"Setup: {state.tweaks_variant_id or state.selected_setup_id or '(none)'}",
        "",
        "Add:",
        *(f"  {item}" for item in (added or ["none"])),
        "",
        "Remove:",
        *(f"  {item}" for item in (removed or ["none"])),
        "",
        f"Will rebuild command: {command or '(no command)'}",
    ]
    if unsupported:
        labels.extend(["", f"Blocked unsupported tweaks: {', '.join(unsupported)}"])
    labels.extend(["", "Proceed? y/N"])
    return labels


def _tweaks_edit_labels(state):
    """Build the left-pane label list for tweaks-edit mode.

    Walks `tweaks_edit_options(state)` (one entry per togglable patch) and
    inserts a non-selectable group header (rendered with leading "-- ") above
    the first patch in each group. Group headers are visual-only and do not
    affect `selected_index`.
    """
    options = tweaks_edit_options(state)
    by_id = {opt.value: opt.label for opt in options}
    labels = []
    for group, patch_ids in tweaks_edit_groups(state):
        labels.append(f"-- {group} --")
        for patch_id in patch_ids:
            label = by_id.get(patch_id)
            if label is not None:
                labels.append(label)
    return labels


def tweaks_detail_text(state) -> str:
    """Right-pane content describing the currently selected patch."""
    patch = selected_tweaks_edit_patch(state)
    if patch is None:
        return "No patch selected."
    applied = "yes" if patch.id in (state.tweaks_baseline or ()) else "no"
    pending = "yes" if patch.id in (state.tweaks_pending or ()) else "no"
    blacklist = ", ".join(patch.versions_blacklisted) if patch.versions_blacklisted else "(none)"
    tested = ", ".join(patch.versions_tested) if patch.versions_tested else "(none)"
    description = patch.description or "(no description)"
    return "\n".join([
        patch.name,
        f"Group: {patch.group}",
        f"Status: {tweak_status(state, patch.id)['label']}",
        f"Reason: {tweak_status(state, patch.id)['reason']}",
        "",
        description,
        "",
        f"Versions supported: {patch.versions_supported}",
        f"Tested ranges: {tested}",
        f"Blacklisted: {blacklist}",
        f"On miss: {patch.on_miss}",
        "",
        f"Enabled in setup {state.tweaks_variant_id or '(no setup)'}: {applied}",
        f"Pending after apply: {pending}",
    ])


def empty_text(state):
    if state.mode in {"inspect", "extract", "patch-source"}:
        return "No centralized native downloads found."
    if state.mode == "patch-package":
        return "No patch bundles found."
    if state.mode == "dashboard" and state.dashboard_step == 1:
        return "No curated dashboard patches available."
    if state.mode in {"variants", "first-run-setup"}:
        return "No setup providers found."
    if state.mode == "tweaks-source":
        return "No setups found - create one first."
    if state.mode in {"tweaks-edit", "tweak-editor"}:
        return "No tweaks match current search/filter."
    return "Ready."


def selected_label_index(state):
    """Map state.selected_index (which walks selectable options) to the row
    index in `current_labels()`. Modes with non-selectable header rows (like
    tweaks-edit's group headers) need this offset.
    """
    if state.mode in {"tweaks-edit", "tweak-editor"} and state.tweak_apply_preview:
        return 0
    if state.mode in {"tweaks-edit", "tweak-editor"}:
        target = state.selected_index
        label_index = 1
        seen = 0
        for _, patch_ids in tweaks_edit_groups(state):
            label_index += 1  # group header
            for _ in patch_ids:
                if seen == target:
                    return label_index
                label_index += 1
                seen += 1
        return max(0, label_index - 1)
    if state.mode == "setup-manager":
        return state.selected_index + 2
    if state.mode == "setup-detail":
        return state.selected_index + len(setup_detail_lines(state)) + 2
    return state.selected_index


def visible_items(labels, selected_index, max_items):
    if not labels:
        return None
    max_items = max(1, max_items)
    if len(labels) <= max_items:
        return 0, labels
    half = max_items // 2
    start = max(0, selected_index - half)
    start = min(start, len(labels) - max_items)
    return start, labels[start:start + max_items]


def clamp_ratio(value):
    return max(0.0, min(float(value), 1.0))


def ascii_progress(title, ratio, label, width=24):
    ratio = clamp_ratio(ratio)
    filled = int(round(ratio * width))
    return f"{title}: [{'#' * filled}{'.' * (width - filled)}] {label}"


def progress_specs(state):
    specs = []
    if state.mode == "dashboard":
        specs.append((
            "Wizard",
            (state.dashboard_step + 1) / len(DASHBOARD_STEPS),
            f"{state.dashboard_step + 1}/{len(DASHBOARD_STEPS)} {DASHBOARD_STEPS[state.dashboard_step]}",
        ))
        if state.dashboard_step == 1:
            specs.append(_dashboard_tweak_progress_spec(state))
    elif state.mode == "patch-package":
        specs.append(_patch_progress_spec(state))
    elif state.mode in {"variants", "first-run-setup"}:
        specs.append((
            "Setup",
            (state.variant_step + 1) / len(VARIANT_STEPS),
            f"{state.variant_step + 1}/{len(VARIANT_STEPS)} {VARIANT_STEPS[state.variant_step]}",
        ))
    return specs


def _patch_progress_spec(state):
    selected = len(selected_dashboard_packages(state))
    total = len(state.patch_packages)
    ratio = selected / total if total else 0.0
    return ("Patch bundles", ratio, f"{selected}/{total} selected")


def _dashboard_tweak_progress_spec(state):
    selected = len(selected_dashboard_tweaks(state))
    available = len(dashboard_tweak_ids())
    ratio = selected / available if available else 0.0
    return ("Tweaks", ratio, f"{selected}/{available} selected")


# -- Compact chrome / key hints -----------------------------------------------

def top_chrome_lines(state):
    return [
        f"cc-extractor | {compact_tab_bar(state)}",
        context_line(state),
    ]


def context_line(state):
    if state.mode == "loading":
        return "Loading | Refreshing setup state"
    if state.mode == "setup-manager":
        return f"Home | Setups {len(state.variants)} | {setup_manager_control_summary(state)}"
    if state.mode == "setup-detail":
        return f"Home > {state.selected_setup_id or 'setup'}"
    if state.mode == "upgrade-preview":
        return f"Home > {state.selected_setup_id or 'setup'} > Upgrade"
    if state.mode == "create-preview":
        return "Create setup > Preview"
    if state.mode == "delete-confirm":
        return f"Home > {state.selected_setup_id or 'setup'} > Delete"
    if state.mode == "health-result":
        return f"Home > {state.selected_setup_id or 'setup'} > Result"
    if state.mode == "help":
        return f"Help | Return {state.help_return_mode or 'setup-manager'}"
    if state.mode == "first-run-setup":
        provider = selected_variant_provider(state)
        name = state.variant_name or (provider.get("defaultVariantName") if provider else "")
        return (
            f"First run setup {VARIANT_STEPS[state.variant_step]} | "
            f"Step {state.variant_step + 1}/{len(VARIANT_STEPS)} | "
            f"Provider {provider.get('key') if provider else 'none'} | "
            f"Name {name or 'none'}"
        )
    if state.mode == "dashboard":
        step = DASHBOARD_STEPS[state.dashboard_step]
        profile = loaded_profile(state)
        profile_label = profile.name if profile else "none"
        return (
            f"Dashboard {step} | Step {state.dashboard_step + 1}/{len(DASHBOARD_STEPS)} | "
            f"Source {dashboard_source_label(state)} | "
            f"Patches {len(selected_dashboard_tweaks(state))} | Profile {profile_label}"
        )
    if state.mode == "variants":
        provider = selected_variant_provider(state)
        name = state.variant_name or (provider.get("defaultVariantName") if provider else "")
        credential = state.variant_credential_env or "none"
        return (
            f"Create setup {VARIANT_STEPS[state.variant_step]} | "
            f"Step {state.variant_step + 1}/{len(VARIANT_STEPS)} | "
            f"Provider {provider.get('key') if provider else 'none'} | "
            f"Name {name or 'none'} | Credential {credential}"
        )
    if state.mode == "patch-package":
        selected = len(selected_dashboard_packages(state))
        total = len(state.patch_packages)
        return f"Patch bundles | Bundles {selected}/{total} selected"
    if state.mode == "tweaks-source":
        return f"Tweaks | Setups {len(state.variants)}"
    if state.mode in {"tweaks-edit", "tweak-editor"}:
        pending = len(set(state.tweaks_pending) ^ set(state.tweaks_baseline))
        return (
            f"Home > {state.tweaks_variant_id or 'setup'} > Edit tweaks | "
            f"{tweak_control_summary(state)} | Pending changes {pending}"
        )
    if state.mode in {"inspect", "extract", "patch-source"}:
        return f"{active_tab(state)} | Native artifacts {len(state.native_artifacts)}"
    return active_tab(state)


def context_hint(state):
    if state.mode == "setup-manager":
        if getattr(state, "setup_search_active", False):
            return "Type to search setups. Enter or Esc keeps the current filter."
        return "Pick a setup, run it, or use a lifecycle action."
    if state.mode == "delete-confirm":
        return "Type the exact setup id, then press Enter."
    if state.mode == "upgrade-preview":
        return "Press y to proceed or n to cancel."
    if state.mode == "create-preview":
        return "Press y to create this setup or n to return to review."
    if state.mode in {"tweaks-edit", "tweak-editor"} and state.tweak_apply_preview:
        return "Review the diff, then press y to rebuild or n to cancel."
    if state.mode in {"tweaks-edit", "tweak-editor"} and getattr(state, "tweak_search_active", False):
        return "Type to search tweaks. Enter or Esc keeps the current filter."
    if state.mode == "dashboard" and state.dashboard_step == 2:
        return "Profile names: select Name, then type or Backspace."
    if state.mode in {"variants", "first-run-setup"}:
        if state.variant_step == 1:
            return "Setup names: select Name, then type or Backspace."
        if state.variant_step == 2:
            return "Credential env: select row, then type or Backspace. Raw API keys are not accepted."
        if state.variant_step == 3:
            return "Model aliases: select row, then type or Backspace. Empty rows use provider defaults."
    return "Ready"


def status_line(state):
    message = state.message.strip() if state.message else context_hint(state)
    return f"Status: {message}"


def meta_line(state):
    counts = f" | {state.counts}" if state.counts else ""
    return f"Theme: {theme_name(state.theme_id)} | Workspace: {workspace_root()}{counts}"


def footer_lines(state):
    return [status_line(state), key_line(state), meta_line(state)]


def footer_text(state):
    return " ".join(line for line in footer_lines(state) if line)


def _dashboard_key_line(state):
    if state.dashboard_step == 0:
        action = "Enter choose | Refresh R"
    elif state.dashboard_step == 1:
        action = "Space toggle | Enter choose"
    elif state.dashboard_step == 3:
        action = "Enter run"
    else:
        action = "Enter choose"
    return f"Keys: Tabs Left/Right/Tab | Move Up/Down | {action} | Back B/Esc | Theme T | Quit Q"


def _variant_key_line(state):
    if state.variant_step == 4:
        action = "Space toggle tweak | V view | Enter choose"
    elif state.variant_step == 5:
        action = "Enter choose"
    elif state.variant_step in {1, 2, 3}:
        action = "Type text | Enter choose"
    else:
        action = "Enter choose"
    return f"Keys: Tabs Left/Right/Tab | Move Up/Down | {action} | Back B/Esc | Theme T | Quit Q"


def key_line(state):
    if state.mode == "setup-manager":
        return "Keys: Up/Down move | Enter manage | X run | / search | P provider | S sort | ? help | N new | U upgrade | T tweaks | H health | D delete | R refresh | Q quit"
    if state.mode == "setup-detail":
        return "Keys: Enter select | X run | Esc back | H health | U upgrade | T tweaks | D delete | C command | G config | L logs | ? help | Q quit"
    if state.mode == "delete-confirm":
        return "Keys: Type setup name | Enter delete | Esc cancel"
    if state.mode == "upgrade-preview":
        return "Keys: Y proceed | N/Esc cancel"
    if state.mode == "create-preview":
        return "Keys: Y create | N/Esc cancel"
    if state.mode == "health-result":
        return "Keys: Esc back | Enter manage | C copy logs | L logs | ? help | Q quit"
    if state.mode == "logs":
        return "Keys: C copy logs | Esc back | ? help | Q quit"
    if state.mode == "help":
        return "Keys: Esc back | Q quit"
    if state.mode == "first-run-setup":
        return _variant_key_line(state)
    if state.mode == "dashboard":
        return _dashboard_key_line(state)
    if state.mode == "patch-package":
        return "Keys: Tabs Left/Right/Tab | Move Up/Down | Space toggle | Enter apply | Back B/Esc | Theme T | Quit Q"
    if state.mode == "variants":
        return _variant_key_line(state)
    if state.mode == "tweaks-source":
        return "Keys: Tabs Left/Right/Tab | Move Up/Down | Enter pick setup | Back B/Esc | Theme T | Quit Q"
    if state.mode in {"tweaks-edit", "tweak-editor"}:
        if state.tweak_apply_preview:
            return "Keys: Y proceed | N/Esc cancel"
        return "Keys: / search | Space toggle | A apply | D discard | V view | Esc back"
    return "Keys: Tabs Left/Right/Tab | Move Up/Down | Enter run | Theme T | Quit Q"


# -- Text fallback (for headless) ---------------------------------------------

def screen_text(state, height=24):
    top_height, footer_height = layout_heights(height)
    body_height = max(3, height - top_height - footer_height)
    lines = top_chrome_lines(state) + [""]

    title, labels = current_labels(state)
    lines.append(title)
    cursor = selected_label_index(state)
    visible = visible_items(labels, cursor, max(1, body_height - 2))
    if visible:
        start_index, visible_labels = visible
        for offset, label in enumerate(visible_labels):
            index = start_index + offset
            prefix = "> " if index == cursor else "  "
            lines.append(prefix + label)
    else:
        lines.append("  " + empty_text(state))

    if state.mode in {"tweaks-edit", "tweak-editor"} and not state.tweak_apply_preview:
        added, removed = tweak_diff(state)
        lines.append("")
        lines.append("Pending changes")
        lines.append("  Add: " + (", ".join(added) if added else "none"))
        lines.append("  Remove: " + (", ".join(removed) if removed else "none"))
        lines.append("")
        lines.append("Tweak details")
        for line in tweaks_detail_text(state).splitlines():
            lines.append("  " + line)

    lines.append("")
    lines.extend(footer_lines(state))
    return "\n".join(lines)


def body_text(state, height):
    title, labels = current_labels(state)
    lines = [title]
    cursor = selected_label_index(state)
    visible = visible_items(labels, cursor, max(1, height - 3))
    if visible:
        start_index, visible_labels = visible
        for offset, label in enumerate(visible_labels):
            index = start_index + offset
            prefix = "> " if index == cursor else "  "
            lines.append(prefix + label)
    else:
        lines.append("  " + empty_text(state))
    return "\n".join(lines)


# -- ratatui-backed rendering -------------------------------------------------

def style(Style, Color, fg: Optional[str] = None, bg: Optional[str] = None, bold: bool = False):
    s = Style(fg=color(Color, fg), bg=color(Color, bg))
    if bold:
        s = s.bold()
    return s


def color(Color, name: Optional[str]):
    return getattr(Color, name or "Reset")


def status_style(state, Style, Color):
    theme = active_theme(state)
    lowered = state.message.lower()
    if "failed" in lowered or "invalid" in lowered or "missing" in lowered or "broken" in lowered:
        return style(Style, Color, theme.error_fg, theme.footer_bg, bold=True)
    if "warning" in lowered:
        return style(Style, Color, theme.warning_fg, theme.footer_bg, bold=True)
    if "complete" in lowered or "created" in lowered or "loaded" in lowered or "healthy" in lowered:
        return style(Style, Color, theme.success_fg, theme.footer_bg, bold=True)
    return style(Style, Color, theme.warning_fg, theme.footer_bg)


def tabs_widget(state, Tabs, Style, Color, theme):
    tabs = Tabs()
    tabs.set_titles(TABS)
    tabs.set_selected(active_tab_index(state))
    tabs.set_divider(" | ")
    tabs.set_block_title("Tabs", True)
    tabs.set_styles(
        style(Style, Color, theme.tab_fg, theme.tab_bg),
        style(Style, Color, theme.tab_selected_fg, theme.tab_selected_bg, bold=True),
    )
    return tabs


def list_widget(state, height, TuiList, Style, Color, theme):
    title, labels = current_labels(state)
    body = TuiList()
    body.set_block_title(title, True)
    body.set_highlight_symbol(">> ")
    body.set_highlight_style(
        style(Style, Color, theme.highlight_fg, theme.highlight_bg, bold=True)
    )

    if labels:
        for label in labels:
            role = _label_role(label)
            fg = {
                "success": theme.success_fg,
                "warning": theme.warning_fg,
                "error": theme.error_fg,
            }.get(role, theme.body_fg)
            body.append_item(label, style(Style, Color, fg, theme.body_bg))
        cursor = selected_label_index(state)
        body.set_selected(cursor)
        body.set_scroll_offset(max(0, cursor - max(0, height // 2)))
    else:
        body.append_item(empty_text(state), style(Style, Color, theme.body_fg, theme.body_bg))
        body.set_selected(None)
    return body


def tweaks_detail_widget(state, Paragraph, Style, Color, theme):
    """Right-pane Paragraph for tweaks-edit mode."""
    text = tweaks_detail_text(state)
    paragraph = Paragraph.from_text(text)
    paragraph.set_block_title("Tweak details", True)
    paragraph.set_style(style(Style, Color, theme.body_fg, theme.body_bg))
    paragraph.set_wrap(True)
    return paragraph


def gauge_widget(title, ratio, label, Gauge, Style, Color, theme):
    gauge = Gauge()
    gauge.ratio(clamp_ratio(ratio))
    gauge.label(label)
    gauge.set_block_title(title, True)
    gauge.set_styles(
        style(Style, Color, theme.gauge_fg, theme.gauge_bg),
        style(Style, Color, theme.gauge_label_fg, theme.gauge_label_bg, bold=True),
        style(Style, Color, theme.gauge_fill_fg, theme.gauge_fill_bg, bold=True),
    )
    return gauge


_BOX_TOP_LEFT = "\u250c"
_BOX_TOP_RIGHT = "\u2510"
_BOX_BOTTOM_LEFT = "\u2514"
_BOX_BOTTOM_RIGHT = "\u2518"
_BOX_HORIZONTAL = "\u2500"
_BOX_VERTICAL = "\u2502"


def _fit_text(text, width):
    if width <= 0:
        return ""
    text = str(text).replace("\n", " ")
    if len(text) > width:
        return text[:width]
    return text + (" " * (width - len(text)))


def _box_top(title, width):
    if width <= 1:
        return _fit_text(title, width)
    inner_width = width - 2
    label = str(title)[:inner_width]
    return _BOX_TOP_LEFT + label + (_BOX_HORIZONTAL * (inner_width - len(label))) + _BOX_TOP_RIGHT


def _box_middle(text, width):
    if width <= 1:
        return _fit_text(text, width)
    return _BOX_VERTICAL + _fit_text(text, width - 2) + _BOX_VERTICAL


def _box_bottom(width):
    if width <= 1:
        return _BOX_HORIZONTAL[:width]
    return _BOX_BOTTOM_LEFT + (_BOX_HORIZONTAL * (width - 2)) + _BOX_BOTTOM_RIGHT


def _single_role_row(text, role):
    return [(text, role)]


def _box_rows(title, content_rows, width, height, role):
    if height <= 0:
        return []
    if height == 1:
        return [_single_role_row(_fit_text(title, width), role)]

    rows = [_single_role_row(_box_top(title, width), role)]
    if height > 2:
        visible_rows = list(content_rows)[:height - 2]
        while len(visible_rows) < height - 2:
            visible_rows.append(("", role))
        for row in visible_rows:
            if isinstance(row, tuple):
                text, row_role = row
            else:
                text, row_role = row, role
            rows.append(_single_role_row(_box_middle(text, width), row_role))
    rows.append(_single_role_row(_box_bottom(width), role))
    return rows[:height]


def _body_content_rows(state, height):
    _, labels = current_labels(state)
    cursor = selected_label_index(state)
    visible = visible_items(labels, cursor, max(1, height))
    if not visible:
        return [(f"  {empty_text(state)}", "body")]

    rows = []
    start_index, visible_labels = visible
    for offset, label in enumerate(visible_labels):
        index = start_index + offset
        selected = index == cursor
        prefix = "> " if selected else "  "
        rows.append((prefix + label, "highlight" if selected else _label_role(label)))
    return rows


def _label_role(label):
    lowered = str(label).lower()
    if " broken" in lowered or "blocked:" in lowered or "unsupported" in lowered:
        return "error"
    if " warning" in lowered or "advanced" in lowered or "unknown" in lowered:
        return "warning"
    if " healthy" in lowered or " ready" in lowered:
        return "success"
    return "body"


def _body_box_rows(state, width, height):
    title, _ = current_labels(state)
    return _box_rows(title, _body_content_rows(state, max(1, height - 2)), width, height, "body")


def _tweaks_detail_box_rows(state, width, height):
    detail_rows = [(line, "body") for line in tweaks_detail_text(state).splitlines()]
    return _box_rows("Tweak details", detail_rows, width, height, "body")


def _combine_segment_rows(left_rows, right_rows, gap_width):
    gap = " " * max(0, gap_width)
    rows = []
    for left, right in zip(left_rows, right_rows):
        rows.append(left + [(gap, "body")] + right)
    return rows


def _tweaks_two_pane_rows(state, width, height):
    if width <= 1:
        return _body_box_rows(state, width, height)
    gap = 1
    left_width = max(1, int((width - gap) * 0.45))
    right_width = max(1, width - gap - left_width)
    left_rows = _body_box_rows(state, left_width, height)
    right_rows = _tweaks_detail_box_rows(state, right_width, height)
    return _combine_segment_rows(left_rows, right_rows, gap)


def _progress_box_rows(title, ratio, label, width):
    progress_width = max(4, min(24, width - len(title) - len(label) - 8))
    return _box_rows(title, [ascii_progress(title, ratio, label, width=progress_width)], width, 3, "gauge")


def layout_heights(height):
    height = max(1, height)
    if height >= 16:
        return 4, 5
    if height >= 12:
        return 3, 4
    top_height = 1
    footer_height = min(2, max(0, height - top_height - 1))
    return top_height, footer_height


def _plain_rows(lines, width, role):
    return [_single_role_row(_fit_text(line, width), role) for line in lines]


def _minimal_frame_rows(state, width, height):
    rows = _plain_rows([top_chrome_lines(state)[0]], width, "header")
    footer_candidates = [status_line(state), key_line(state)]
    footer_height = min(len(footer_candidates), max(0, height - len(rows) - 1))
    body_height = max(1, height - len(rows) - footer_height)
    body_rows = body_text(state, body_height).splitlines()[:body_height]
    rows.extend(_plain_rows(body_rows, width, "body"))
    rows.extend(_plain_rows(footer_candidates[:footer_height], width, "footer"))
    return rows[:height]


def _frame_rows(state, width, height):
    width = max(1, width)
    height = max(1, height)
    if height < 12:
        rows = _minimal_frame_rows(state, width, height)
        if len(rows) < height:
            rows.extend(_single_role_row(_fit_text("", width), "body") for _ in range(height - len(rows)))
        return rows[:height]

    top_height, footer_height = layout_heights(height)
    body_height = max(1, height - top_height - footer_height)

    rows = _box_rows("", top_chrome_lines(state), width, top_height, "header")
    if state.mode in {"tweaks-edit", "tweak-editor"} and not state.tweak_apply_preview and width > 60:
        rows.extend(_tweaks_two_pane_rows(state, width, body_height))
    else:
        rows.extend(_body_box_rows(state, width, body_height))
    rows.extend(_box_rows("Status", footer_lines(state), width, footer_height, "footer"))

    if len(rows) < height:
        rows.extend(_single_role_row(_fit_text("", width), "body") for _ in range(height - len(rows)))
    return rows[:height]


def _frame_styles(state, Style, Color, theme):
    return {
        "header": style(Style, Color, theme.header_fg, theme.header_bg, bold=True),
        "tabs": style(Style, Color, theme.tab_fg, theme.tab_bg),
        "body": style(Style, Color, theme.body_fg, theme.body_bg),
        "highlight": style(Style, Color, theme.highlight_fg, theme.highlight_bg, bold=True),
        "success": style(Style, Color, theme.success_fg, theme.body_bg),
        "warning": style(Style, Color, theme.warning_fg, theme.body_bg),
        "error": style(Style, Color, theme.error_fg, theme.body_bg, bold=True),
        "gauge": style(Style, Color, theme.gauge_fg, theme.gauge_bg),
        "footer": status_style(state, Style, Color),
    }


def render_frame(term, state, width, height, Paragraph, Style, Color, DrawCmd, Tabs, TuiList, Gauge):
    width = max(1, width)
    height = max(1, height)
    theme = active_theme(state)
    frame = Paragraph.new_empty()
    styles = _frame_styles(state, Style, Color, theme)
    for row_index, row in enumerate(_frame_rows(state, width, height)):
        if row_index:
            frame.line_break()
        for text, role in row:
            frame.append_span(text, styles[role])
    frame.set_wrap(False)
    term.draw_frame([DrawCmd.paragraph(frame, (0, 0, width, height))])
