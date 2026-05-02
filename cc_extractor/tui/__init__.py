"""Interactive TUI for cc-extractor.

The action layer (mode dispatchers, build runners, key handlers, monkey-patch
re-exports) lives in this ``__init__`` module so test fixtures can do
``monkeypatch.setattr(tui, "create_variant", fake)`` and have the patch propagate
to internal call sites.

Pure helpers live in submodules (``state``, ``themes``, ``options``,
``rendering``, ``nav``, ``keys``, ``dashboard``, ``variant_actions``) and are
re-exported below to keep the existing ``tui._foo`` test API stable.
"""

import os
from pathlib import Path

__all__ = [
    "TUI_THEMES", "TuiTheme",
    "apply_dashboard_tweaks_to_native", "apply_patch_packages_to_native", "apply_variant",
    "create_variant", "doctor_variant", "load_variant", "remove_variant", "update_variants",
    "download_binary", "download_versions", "extract_all",
    "load_download_index", "list_variant_providers", "parse_bun_binary",
    "provider_default_variant_name", "refresh_download_index", "scan_variants",
    "CURATED_TWEAK_IDS", "DASHBOARD_TWEAK_IDS", "DEFAULT_TWEAK_IDS",
    "DashboardTweakProfile", "NativeArtifact", "PatchPackage", "PatchProfile",
    "delete_dashboard_tweak_profile", "delete_patch_profile", "extraction_paths",
    "load_dashboard_tweak_profile", "load_patch_profile",
    "load_tui_settings", "native_artifact_from_path", "rename_dashboard_tweak_profile", "rename_patch_profile",
    "save_dashboard_tweak_profile", "save_patch_profile", "save_tui_settings", "scan_dashboard_tweak_profiles",
    "scan_extractions", "scan_native_downloads", "scan_npm_downloads", "scan_patch_packages",
    "scan_patch_profiles", "short_sha", "workspace_root",
    "DASHBOARD_STEPS", "DEFAULT_THEME_ID", "MenuOption", "SOURCE_ARTIFACT",
    "SOURCE_LATEST", "SOURCE_VERSION", "TABS", "TAB_MODES", "THEME_ORDER",
    "VARIANT_MODEL_FIELDS", "VARIANT_STEPS",
    "_active_tab", "_body_text", "_footer_lines", "_footer_text", "_gauge_widget",
    "_list_widget", "_tabs_widget", "_normalize_theme_id", "_theme_name",
    "_dashboard_options", "_dashboard_source_artifact", "_dashboard_tweak_ids", "_loaded_profile",
    "_dashboard_tweak_profile_by_id", "_dashboard_tweak_profile_missing_ids",
    "_profile_by_id", "_profile_missing_refs", "_profile_refs_by_key",
    "_selected_dashboard_tweaks", "_selected_patch_refs", "_selected_setup_option", "_selected_setup_variant",
    "_variant_model_display_value", "_variant_options",
    "_selected_artifact",
    "_run_quiet",
    "_advance_dashboard", "_create_dashboard_profile", "_dashboard_artifact_for_run",
    "_delete_dashboard_profile", "_load_dashboard_profile", "_overwrite_dashboard_profile",
    "_refresh_dashboard_index", "_rename_dashboard_profile", "_require_dashboard_patches",
    "_reset_dashboard", "_toggle_dashboard_patch", "_toggle_dashboard_tweak",
    "_dashboard_accepts_profile_text", "_dashboard_backspace",
    "_variant_accepts_text", "_variant_append_text", "_variant_backspace",
    "_activate_extract", "_activate_inspect", "_activate_patch_source",
    "_apply_tweaks", "_discard_tweaks", "_enter_tweaks_for_variant",
    "_go_back", "_move_tab", "_selected_tweaks_source_variant_id",
    "_set_mode", "_source_artifact", "_toggle_patch", "_toggle_tweak",
    "_tweaks_edit_options", "_tweaks_source_options",
    "_selected_dashboard_option", "_selected_dashboard_packages",
    "_selected_variant_option", "_selected_variant_provider",
    "_active_theme", "_cycle_theme", "_load_saved_theme_id",
    "_advance_variant", "_require_variant_model_mapping", "_reset_variant",
    "_set_variant_provider_defaults", "_toggle_variant_tweak",
    "_variant_credential_env_for_create", "_variant_model_overrides_for_create",
    "_run_setup_health", "_run_setup_upgrade", "_run_setup_delete", "_route_startup",
    "_screen_text", "_style", "_render_frame",
    "run_tui",
]

# Externally-supplied helpers that tests monkey-patch through ``tui.<name>``.
# Imports must stay in this module so internal callers resolve through the
# package globals that ``monkeypatch.setattr`` updates.
from ..bun_extract import parse_bun_binary
from ..download_index import download_versions, load_download_index, refresh_download_index
from ..downloader import download_binary
from ..extractor import extract_all
from ..patch_workflow import apply_dashboard_tweaks_to_native, apply_patch_packages_to_native
from ..providers import provider_default_variant_name
from ..variant_tweaks import CURATED_TWEAK_IDS, DASHBOARD_TWEAK_IDS, DEFAULT_TWEAK_IDS
from ..variants import (
    apply_variant,
    create_variant,
    doctor_variant,
    list_variant_providers,
    load_variant,
    remove_variant,
    scan_variants,
    update_variants,
)
from ..variants.model import variant_id_from_name
from ..workspace import (
    DashboardTweakProfile,
    NativeArtifact,
    PatchPackage,
    PatchProfile,
    delete_dashboard_tweak_profile,
    delete_patch_profile,
    extraction_paths,
    load_dashboard_tweak_profile,
    load_patch_profile,
    load_tui_settings,
    native_artifact_from_path,
    rename_dashboard_tweak_profile,
    rename_patch_profile,
    save_dashboard_tweak_profile,
    save_patch_profile,
    save_tui_settings,
    scan_dashboard_tweak_profiles,
    scan_extractions,
    scan_native_downloads,
    scan_npm_downloads,
    scan_patch_packages,
    scan_patch_profiles,
    short_sha,
    workspace_root,
)

from ._const import (
    DASHBOARD_STEPS,
    DEFAULT_THEME_ID,
    MenuOption,
    SOURCE_ARTIFACT,
    SOURCE_LATEST,
    SOURCE_VERSION,
    TABS,
    TAB_MODES,
    THEME_ORDER,
    VARIANT_MODEL_FIELDS,
    VARIANT_STEPS,
)
from ._runtime import run_quiet as _run_quiet
from .dashboard import (
    advance_dashboard as _advance_dashboard,
    create_dashboard_profile as _create_dashboard_profile,
    dashboard_artifact_for_run as _dashboard_artifact_for_run,
    delete_dashboard_profile as _delete_dashboard_profile,
    load_dashboard_profile as _load_dashboard_profile,
    overwrite_dashboard_profile as _overwrite_dashboard_profile,
    refresh_dashboard_index as _refresh_dashboard_index,
    rename_dashboard_profile as _rename_dashboard_profile,
    require_dashboard_patches as _require_dashboard_patches,
    reset_dashboard as _reset_dashboard,
    toggle_dashboard_patch as _toggle_dashboard_patch,
    toggle_dashboard_tweak as _toggle_dashboard_tweak,
)
from .keys import (
    dashboard_accepts_profile_text as _dashboard_accepts_profile_text,
    dashboard_backspace as _dashboard_backspace,
    variant_accepts_text as _variant_accepts_text,
    variant_append_text as _variant_append_text,
    variant_backspace as _variant_backspace,
)
from .nav import (
    activate_extract as _activate_extract,
    activate_inspect as _activate_inspect,
    activate_patch_source as _activate_patch_source,
    apply_tweaks as _apply_tweaks,
    discard_tweaks as _discard_tweaks,
    enter_tweaks_for_variant as _enter_tweaks_for_variant,
    go_back as _go_back,
    move_tab as _move_tab,
    selected_artifact as _selected_artifact,
    set_mode as _set_mode,
    source_artifact as _source_artifact,
    toggle_patch as _toggle_patch,
    toggle_tweak as _toggle_tweak,
)
from .options import (
    dashboard_tweak_ids as _dashboard_tweak_ids,
    dashboard_options as _dashboard_options,
    dashboard_source_artifact as _dashboard_source_artifact,
    dashboard_tweak_profile_by_id as _dashboard_tweak_profile_by_id,
    dashboard_tweak_profile_missing_ids as _dashboard_tweak_profile_missing_ids,
    loaded_profile as _loaded_profile,
    profile_by_id as _profile_by_id,
    profile_missing_refs as _profile_missing_refs,
    profile_refs_by_key as _profile_refs_by_key,
    selected_dashboard_option as _selected_dashboard_option,
    selected_dashboard_packages as _selected_dashboard_packages,
    selected_dashboard_tweaks as _selected_dashboard_tweaks,
    selected_patch_refs as _selected_patch_refs,
    selected_setup_option as _selected_setup_option,
    selected_setup_variant as _selected_setup_variant,
    selected_tweaks_source_variant_id as _selected_tweaks_source_variant_id,
    selected_variant_option as _selected_variant_option,
    selected_variant_provider as _selected_variant_provider,
    tweak_diff as _tweak_diff,
    unsupported_pending_tweaks as _unsupported_pending_tweaks,
    tweaks_edit_options as _tweaks_edit_options,
    tweaks_source_options as _tweaks_source_options,
    variant_model_display_value as _variant_model_display_value,
    variant_options as _variant_options,
)
from .rendering import (
    active_tab as _active_tab,
    body_text as _body_text,
    footer_lines as _footer_lines,
    footer_text as _footer_text,
    gauge_widget as _gauge_widget,
    list_widget as _list_widget,
    render_frame as _render_frame,
    screen_text as _screen_text,
    style as _style,
    tabs_widget as _tabs_widget,
)
from .state import TuiState
from .themes import (
    TUI_THEMES,
    TuiTheme,
    active_theme as _active_theme,
    cycle_theme as _cycle_theme,
    load_saved_theme_id as _load_saved_theme_id,
    normalize_theme_id as _normalize_theme_id,
    theme_name as _theme_name,
)
from .variant_actions import (
    advance_variant as _advance_variant,
    require_variant_model_mapping as _require_variant_model_mapping,
    reset_variant as _reset_variant,
    set_variant_provider_defaults as _set_variant_provider_defaults,
    toggle_variant_tweak as _toggle_variant_tweak,
    variant_credential_env_for_create as _variant_credential_env_for_create,
    variant_model_overrides_for_create as _variant_model_overrides_for_create,
)


# -- Top-level event loop ----------------------------------------------------

def run_tui():
    try:
        from ratatui_py import (
            App,
            Color,
            DrawCmd,
            Gauge,
            KeyCode,
            List as TuiList,
            Paragraph,
            Style,
            Tabs,
        )
    except (ImportError, OSError, RuntimeError) as exc:
        raise RuntimeError(f"ratatui is unavailable: {exc}") from exc

    state = TuiState(theme_id=_load_saved_theme_id())
    if _refresh_state(state):
        _route_startup(state)

    def render(term, app_state):
        width, height = term.size()
        try:
            _render_frame(
                term, app_state, width, height,
                Paragraph, Style, Color, DrawCmd, Tabs, TuiList, Gauge,
            )
        except Exception:
            theme = _active_theme(app_state)
            screen = Paragraph.from_text(_screen_text(app_state, height=max(1, height - 1)))
            screen.set_block_title("cc-extractor", True)
            screen.set_style(_style(Style, Color, theme.body_fg, theme.body_bg, bold=True))
            screen.set_wrap(True)
            term.draw_paragraph(screen, (0, 0, max(1, width - 1), max(1, height - 1)))

    def on_event(term, event, app_state):
        if event.get("kind") != "key":
            return True

        code = event.get("code")
        char_code = event.get("ch") or 0

        if code == int(KeyCode.Up):
            app_state.move(-1)
        elif code == int(KeyCode.Down):
            app_state.move(1)
        elif code == int(KeyCode.Left):
            _move_tab(app_state, -1)
        elif code == int(KeyCode.Right) or code == int(KeyCode.Tab):
            _move_tab(app_state, 1)
        elif code == int(KeyCode.Home):
            app_state.selected_index = 0
        elif code == int(KeyCode.End):
            app_state.selected_index = max(0, app_state.item_count() - 1)
        elif code == int(KeyCode.Backspace):
            if not _handle_backspace_key(app_state):
                _go_back(app_state)
        elif code == int(KeyCode.Esc):
            _go_back(app_state)
        elif code == int(KeyCode.Enter):
            return _activate(app_state)
        elif code == int(KeyCode.Char) and char_code:
            return _handle_char_key(app_state, chr(char_code))

        return True

    def on_start(term, app_state):
        term.enter_alt()
        term.enable_raw()
        term.clear()

    def on_stop(exc, term, app_state):
        term.show_cursor()
        term.disable_raw()
        term.leave_alt()

    app = App(
        render=render,
        on_event=on_event,
        on_start=on_start,
        on_stop=on_stop,
        tick_ms=3_600_000,
        clear_each_frame=True,
    )
    app.run(state)


def _refresh_state(state):
    try:
        state.refresh()
        return True
    except Exception as exc:
        prefix = f"{state.message} " if state.message else ""
        state.message = f"{prefix}Refresh failed: {exc}"
        return False


def _route_startup(state):
    if state.variants:
        if state.selected_setup_id is None:
            state.selected_setup_id = state.variants[0].variant_id
        _set_mode(state, "setup-manager")
    else:
        _reset_variant(state)
        _set_mode(state, "first-run-setup")
        state.message = "No Claude Code setups found."


# -- Key handlers ------------------------------------------------------------

def _handle_backspace_key(state):
    if state.mode == "delete-confirm":
        state.delete_confirm_text = state.delete_confirm_text[:-1]
        return True
    if state.mode == "dashboard":
        return _dashboard_backspace(state)
    if state.mode in {"variants", "first-run-setup"}:
        return _variant_backspace(state)
    return False


def _handle_char_key(state, char):
    if state.mode == "delete-confirm":
        if char.isprintable() and char not in "\r\n\t":
            state.delete_confirm_text += char
        return True

    if state.mode == "dashboard" and _dashboard_accepts_profile_text(state):
        if char.isprintable() and char not in "\r\n\t":
            state.dashboard_profile_name += char
            state.dashboard_delete_confirm_id = ""
        return True

    if state.mode in {"variants", "first-run-setup"} and _variant_accepts_text(state):
        if char.isprintable() and char not in "\r\n\t":
            _variant_append_text(state, char)
        return True

    lowered = char.lower()
    if lowered == "q":
        return False
    if state.mode == "upgrade-preview":
        if lowered == "y":
            _run_setup_upgrade(state)
        elif lowered == "n":
            _go_back(state)
        return True
    if state.mode in {"tweaks-edit", "tweak-editor"} and state.tweak_apply_preview:
        if lowered == "y":
            _run_tweak_apply(state)
            _refresh_state(state)
        elif lowered == "n":
            state.tweak_apply_preview = False
            state.message = "Tweak rebuild cancelled."
        return True
    handled_setup_key = False
    if lowered == "n" and state.mode in {"setup-manager", "setup-detail", "health-result"}:
        _start_setup_create(state)
        handled_setup_key = True
    elif lowered == "u" and state.mode in {"setup-manager", "setup-detail"}:
        _open_upgrade_preview(state)
        handled_setup_key = True
    elif lowered == "h" and state.mode in {"setup-manager", "setup-detail"}:
        setup_id = _current_setup_id_for_action(state)
        if setup_id:
            _run_setup_health(state, setup_id, show_result=True)
        handled_setup_key = True
    elif lowered == "d" and state.mode in {"setup-manager", "setup-detail"}:
        _open_delete_confirm(state)
        handled_setup_key = True
    elif lowered == "t" and state.mode in {"setup-manager", "setup-detail"}:
        _open_tweak_editor(state)
        handled_setup_key = True
    elif lowered == "r" and state.mode == "setup-manager":
        _refresh_state(state)
        state.message = "Setup list refreshed."
        handled_setup_key = True
    elif lowered == "c" and state.mode == "setup-detail":
        state.message = "Copy is not implemented yet. Command path is shown above."
        handled_setup_key = True
    if handled_setup_key:
        return True
    if lowered == "b":
        _go_back(state)
    elif lowered == "t":
        if state.mode not in {"setup-manager", "setup-detail"}:
            _cycle_theme(state)
    elif lowered == "a" and state.mode in {"tweaks-edit", "tweak-editor"}:
        _begin_tweak_apply_preview(state)
    elif lowered == "d" and state.mode in {"tweaks-edit", "tweak-editor"}:
        _discard_tweaks(state)
    elif lowered == "v" and state.mode in {"tweaks-edit", "tweak-editor", "variants", "first-run-setup"}:
        _cycle_tweak_filter(state)
    elif char == " ":
        _toggle_selected(state)
    elif lowered == "r" and state.mode == "dashboard" and state.dashboard_step == 0:
        _refresh_dashboard_index(state)

    return True


def _variant_accepts_name_text(state):
    if state.mode not in {"variants", "first-run-setup"} or state.variant_step != 1:
        return False
    option = _selected_variant_option(state)
    return option is not None and option.kind == "variant-name"


def _toggle_selected(state):
    if state.mode == "dashboard":
        option = _selected_dashboard_option(state)
        if option and option.kind == "dashboard-tweak-toggle":
            _toggle_dashboard_tweak(state, str(option.value))
    elif state.mode == "patch-package":
        _toggle_patch(state)
    elif state.mode in {"variants", "first-run-setup"}:
        option = _selected_variant_option(state)
        if option and option.kind == "variant-tweak":
            _toggle_variant_tweak(state, str(option.value))
    elif state.mode in {"tweaks-edit", "tweak-editor"}:
        _toggle_tweak(state)


# -- Activate dispatchers ----------------------------------------------------

def _activate(state):
    state.message = ""
    try:
        if state.mode == "setup-manager":
            _activate_setup_manager(state)
        elif state.mode == "setup-detail":
            _activate_setup_detail(state)
        elif state.mode == "first-run-setup":
            _activate_variants(state)
        elif state.mode == "upgrade-preview":
            state.message = "Press y to proceed, or n/Esc to cancel."
        elif state.mode == "delete-confirm":
            _run_setup_delete(state)
        elif state.mode == "health-result":
            _set_mode(state, "setup-detail" if state.selected_setup_id else "setup-manager")
        elif state.mode == "dashboard":
            _activate_dashboard(state)
        elif state.mode == "inspect":
            _activate_inspect(state)
        elif state.mode == "extract":
            _activate_extract(state)
        elif state.mode == "patch-source":
            _activate_patch_source(state)
        elif state.mode == "patch-package":
            _activate_patch_packages(state)
        elif state.mode == "variants":
            _activate_variants(state)
        elif state.mode == "tweaks-source":
            _activate_tweaks_source(state)
        elif state.mode in {"tweaks-edit", "tweak-editor"}:
            _activate_tweaks_edit(state)
    except Exception as exc:
        state.message = f"Action failed: {exc}"

    _refresh_state(state)
    return True


def _activate_tweaks_source(state):
    """Enter tweak-editor scoped to the selected setup."""
    variant_id = _selected_tweaks_source_variant_id(state)
    if variant_id is None:
        state.message = "No setup available - create one first."
        return
    _enter_tweaks_for_variant(state, variant_id)


def _activate_tweaks_edit(state):
    """Enter on a patch row toggles it (mirrors Space)."""
    if state.tweak_apply_preview:
        state.message = "Press y to rebuild, or n/Esc to cancel."
        return
    _toggle_tweak(state)


def _activate_setup_manager(state):
    option = _selected_setup_option(state)
    if option is None:
        return
    if option.kind == "setup-action-new":
        _start_setup_create(state)
    elif option.kind == "setup-row":
        state.selected_setup_id = str(option.value)
        _set_mode(state, "setup-detail")


def _activate_setup_detail(state):
    option = _selected_setup_option(state)
    if option is None:
        return
    setup_id = str(option.value) if option.value else _current_setup_id_for_action(state)
    if option.kind == "setup-action-new":
        _start_setup_create(state)
    elif option.kind == "setup-action-health" and setup_id:
        _run_setup_health(state, setup_id, show_result=True)
    elif option.kind == "setup-action-upgrade":
        _open_upgrade_preview(state)
    elif option.kind == "setup-action-tweaks":
        _open_tweak_editor(state)
    elif option.kind == "setup-action-delete":
        _open_delete_confirm(state)


def _current_setup_id_for_action(state):
    option = _selected_setup_option(state)
    if state.mode == "setup-manager":
        if option is None or option.kind != "setup-row":
            state.message = "Select a setup first."
            return None
        return str(option.value)
    setup_id = state.selected_setup_id
    if not setup_id:
        state.message = "Select a setup first."
        return None
    return setup_id


def _start_setup_create(state):
    _reset_variant(state)
    state.tweak_filter = "recommended"
    _set_mode(state, "variants" if state.variants else "first-run-setup")


def _open_upgrade_preview(state):
    setup_id = _current_setup_id_for_action(state)
    if setup_id is None:
        return
    state.selected_setup_id = setup_id
    state.setup_upgrade_target = "latest"
    state.last_action_summary = []
    _set_mode(state, "upgrade-preview")


def _open_delete_confirm(state):
    setup_id = _current_setup_id_for_action(state)
    if setup_id is None:
        return
    state.selected_setup_id = setup_id
    state.delete_confirm_text = ""
    _set_mode(state, "delete-confirm")


def _open_tweak_editor(state):
    setup_id = _current_setup_id_for_action(state)
    if setup_id is None:
        return
    _enter_tweaks_for_variant(state, setup_id)


def _health_status_from_report(report):
    return "healthy" if report and report.get("ok") else "broken"


def _run_setup_health(state, setup_id, *, show_result=False):
    try:
        reports, _output = _run_quiet(doctor_variant, setup_id)
        report = reports[0] if reports else {"id": setup_id, "ok": False, "checks": []}
        status = _health_status_from_report(report)
        checks = report.get("checks", []) or []
        state.setup_health[setup_id] = {
            "status": status,
            "checks": checks,
            "message": f"Health: {status}",
        }
        lines = [f"Setup: {setup_id}", f"Health: {status}"]
        for check in checks:
            check_status = "ok" if check.get("ok") else "failed"
            lines.append(f"{check.get('name', '?')}: {check_status} {check.get('path', '')}")
        state.message = f"Health for setup {setup_id}: {status}"
    except Exception as exc:
        status = "broken"
        state.setup_health[setup_id] = {
            "status": status,
            "checks": [],
            "message": str(exc),
        }
        lines = [f"Setup: {setup_id}", "Health: broken", f"Doctor failed: {exc}"]
        state.message = f"Health for setup {setup_id}: broken"
    if show_result:
        state.selected_setup_id = setup_id
        state.last_action_summary = lines
        message = state.message
        _set_mode(state, "health-result")
        state.message = message
    return state.setup_health[setup_id]


def _run_setup_upgrade(state):
    setup_id = state.selected_setup_id
    variant = _selected_setup_variant(state)
    if not setup_id or variant is None:
        state.message = "Select a setup first."
        return
    old_version = ((variant.manifest or {}).get("source") or {}).get("version") or "?"
    target = state.setup_upgrade_target or "latest"
    try:
        results, _output = _run_quiet(update_variants, setup_id, claude_version=target)
        _refresh_state(state)
        state.selected_setup_id = setup_id
        refreshed = _selected_setup_variant(state)
        new_version = ((refreshed.manifest or {}).get("source") or {}).get("version") if refreshed else "?"
        health = _run_setup_health(state, setup_id, show_result=False)
        wrapper = ""
        if results:
            wrapper = str(getattr(results[0], "wrapper_path", "") or "")
        if not wrapper and refreshed is not None:
            wrapper = str(((refreshed.manifest or {}).get("paths") or {}).get("wrapper") or "")
        status = health.get("status", "unknown")
        state.last_action_summary = [
            f"Setup upgraded: {setup_id}",
            f"Claude Code: {old_version} -> {new_version or target}",
            "Tweaks reapplied: yes",
            f"Command rebuilt path: {wrapper or '(unknown)'}",
            f"Health: {status}",
        ]
        state.message = f"Upgrade complete for setup {setup_id}: {status}"
    except Exception as exc:
        active = "yes"
        try:
            load_variant(setup_id)
        except Exception:
            active = "unknown"
        state.last_action_summary = [
            f"Upgrade failed: {setup_id}",
            "Base download succeeded: unknown",
            "Command replaced: unknown",
            f"Previous setup remains active: {active}",
            f"Failed stage: {exc}",
        ]
        state.message = f"Upgrade failed: {exc}"
    message = state.message
    _set_mode(state, "health-result")
    state.message = message


def _run_setup_delete(state):
    variant = _selected_setup_variant(state)
    if variant is None:
        state.message = "Select a setup first."
        return
    setup_id = variant.variant_id
    if state.delete_confirm_text != setup_id:
        state.message = f"Type {setup_id} exactly to delete."
        return
    paths = (variant.manifest or {}).get("paths") or {}
    setup_dir = variant.path
    wrapper_text = paths.get("wrapper") or ""
    wrapper_path = Path(wrapper_text) if wrapper_text else None
    try:
        removed, _output = _run_quiet(remove_variant, setup_id, yes=True)
        setup_removed = not setup_dir.exists()
        command_removed = True if wrapper_path is None else not wrapper_path.exists()
        state.message = f"Deleted setup {setup_id}." if removed else f"Setup {setup_id} was not found."
    except Exception as exc:
        setup_removed = not setup_dir.exists()
        command_removed = True if wrapper_path is None else not wrapper_path.exists()
        state.message = f"Delete failed: {exc}"
    state.last_action_summary = [
        f"Deleted setup: {setup_id}",
        f"Setup directory removed: {'yes' if setup_removed else 'no'}",
        f"Command removed: {'yes' if command_removed else 'no'}",
        "Shared downloads untouched: yes",
        "Next: refresh setup list or create a new setup.",
    ]
    state.delete_confirm_text = ""
    state.selected_setup_id = None
    _refresh_state(state)
    message = state.message
    _set_mode(state, "setup-manager")
    state.message = message


def _begin_tweak_apply_preview(state):
    if list(state.tweaks_pending) == list(state.tweaks_baseline):
        state.message = "No tweak changes to apply."
        return
    unsupported = _unsupported_pending_tweaks(state)
    if unsupported:
        state.message = f"Unsupported tweaks selected: {', '.join(unsupported)}"
        return
    state.tweak_apply_preview = True
    state.message = "Review tweak diff, then press y to rebuild."


def _run_tweak_apply(state):
    setup_id = state.tweaks_variant_id
    if setup_id is None:
        state.message = "No setup selected."
        return
    added, removed = _tweak_diff(state)
    state.tweak_apply_preview = False
    _apply_tweaks(state)
    if not state.message.startswith("Applied tweaks"):
        state.last_action_summary = [state.message]
        message = state.message
        _set_mode(state, "health-result")
        state.message = message
        return
    state.selected_setup_id = setup_id
    health = _run_setup_health(state, setup_id, show_result=False)
    state.last_tweak_result = {
        "added": added,
        "removed": removed,
        "health": health.get("status", "unknown"),
    }
    state.last_action_summary = [
        "Tweaks updated:",
        f"Added: {', '.join(added) if added else 'none'}",
        f"Removed: {', '.join(removed) if removed else 'none'}",
        "Rebuild: successful",
        f"Health: {health.get('status', 'unknown')}",
    ]
    state.message = f"Tweaks updated for setup {setup_id}: {health.get('status', 'unknown')}"
    message = state.message
    _set_mode(state, "health-result")
    state.message = message


def _cycle_tweak_filter(state):
    order = ["recommended", "all", "advanced", "incompatible"]
    current = state.tweak_filter if state.tweak_filter in order else "recommended"
    state.tweak_filter = order[(order.index(current) + 1) % len(order)]
    state.selected_index = 0
    state.message = f"Tweak view: {state.tweak_filter}"


def _activate_dashboard(state):
    option = _selected_dashboard_option(state)
    if option is None:
        return

    if option.kind != "profile-delete":
        state.dashboard_delete_confirm_id = ""

    if option.kind == "section":
        return
    if option.kind == "source-latest":
        state.dashboard_source_kind = SOURCE_LATEST
        state.dashboard_source_version = ""
        _advance_dashboard(state)
    elif option.kind == "source-version":
        state.dashboard_source_kind = SOURCE_VERSION
        state.dashboard_source_version = option.value
        _advance_dashboard(state)
    elif option.kind == "source-artifact":
        state.dashboard_source_kind = SOURCE_ARTIFACT
        state.dashboard_source_artifact_index = int(option.value)
        _advance_dashboard(state)
    elif option.kind == "refresh-index":
        _refresh_dashboard_index(state)
    elif option.kind == "dashboard-tweak-toggle":
        _toggle_dashboard_tweak(state, str(option.value))
    elif option.kind == "profile-load":
        _load_dashboard_profile(state, str(option.value))
    elif option.kind == "patch-continue":
        if _require_dashboard_patches(state):
            _advance_dashboard(state)
    elif option.kind == "profile-name":
        state.message = "Type a profile name here, then choose a profile action."
    elif option.kind == "profile-create":
        _create_dashboard_profile(state)
    elif option.kind == "profile-rename":
        _rename_dashboard_profile(state, str(option.value))
    elif option.kind == "profile-overwrite":
        _overwrite_dashboard_profile(state, str(option.value))
    elif option.kind == "profile-delete":
        _delete_dashboard_profile(state, str(option.value))
    elif option.kind == "review-continue":
        if _require_dashboard_patches(state):
            _advance_dashboard(state)
    elif option.kind == "review-run":
        _run_dashboard_build(state)
    elif option.kind == "review-back":
        state.dashboard_step = 2
        state.selected_index = 0
    elif option.kind == "review-reset":
        _reset_dashboard(state)


def _activate_variants(state):
    option = _selected_variant_option(state)
    if option is None:
        return
    if option.kind == "section":
        return
    if option.kind == "variant-status":
        try:
            report = doctor_variant(str(option.value))
            ok = report[0]["ok"] if report else False
            state.message = f"Setup {option.value}: {'healthy' if ok else 'broken'}"
        except Exception as exc:
            state.message = f"Setup status failed: {exc}"
    elif option.kind == "variant-provider":
        state.variant_provider_index = int(option.value)
        provider = _selected_variant_provider(state)
        _set_variant_provider_defaults(state, provider)
        _advance_variant(state)
    elif option.kind == "variant-name":
        state.message = "Type a setup name here, then continue."
    elif option.kind == "variant-name-continue":
        if not state.variant_name.strip():
            state.message = "Type a setup name first."
            return
        _advance_variant(state)
    elif option.kind == "variant-credential-env":
        state.message = "Type a credential environment variable name. Raw API keys are not accepted here."
    elif option.kind == "variant-credentials-continue":
        provider = _selected_variant_provider(state)
        if provider and not provider.get("requiresModelMapping"):
            state.variant_step = 4
            state.selected_index = 0
        else:
            _advance_variant(state)
    elif option.kind == "variant-model":
        state.message = f"Type the {option.value} model alias, or clear it to use the provider default."
    elif option.kind == "variant-models-continue":
        if _require_variant_model_mapping(state):
            _advance_variant(state)
    elif option.kind == "variant-tweak":
        _toggle_variant_tweak(state, str(option.value))
    elif option.kind == "variant-tweak-view":
        state.tweak_filter = str(option.value)
        state.selected_index = 0
    elif option.kind == "variant-tweaks-continue":
        _advance_variant(state)
    elif option.kind == "variant-create":
        _run_variant_create(state)
    elif option.kind == "variant-review-back":
        state.variant_step = 4
        state.selected_index = 0
    elif option.kind == "variant-reset":
        _reset_variant(state)


def _activate_patch_packages(state):
    artifact = _source_artifact(state)
    if artifact is None:
        _set_mode(state, "patch-source")
        return
    if not state.selected_patch_indexes:
        state.message = "Select at least one patch package with Space."
        return

    packages = [
        state.patch_packages[index]
        for index in state.selected_patch_indexes
        if 0 <= index < len(state.patch_packages)
    ]
    if not packages:
        state.message = "Selected patch packages are unavailable."
        return
    try:
        result, _output = _run_quiet(apply_patch_packages_to_native, artifact, packages)
        state.message = f"Patched binary: {result.output_path}"
        _set_mode(state, "patch-source")
    except Exception as exc:
        state.message = f"Patch failed: {exc}"


def _run_dashboard_build(state):
    if not _require_dashboard_patches(state):
        return

    loaded_profile = _loaded_profile(state)
    if loaded_profile is not None:
        missing = _dashboard_tweak_profile_missing_ids(state, loaded_profile)
        if missing:
            state.message = f"Loaded profile is invalid, missing {', '.join(missing)}"
            return

    tweak_ids = _selected_dashboard_tweaks(state)
    try:
        artifact = _dashboard_artifact_for_run(state)
        if artifact is None:
            return
        result, _output = _run_quiet(apply_dashboard_tweaks_to_native, artifact, tweak_ids)
        state.message = f"Dashboard build complete: {result.output_path}"
    except Exception as exc:
        state.message = f"Dashboard build failed: {exc}"


def _run_variant_create(state):
    provider = _selected_variant_provider(state)
    if provider is None:
        state.message = "Select a provider first."
        return
    name = state.variant_name.strip() or provider_default_variant_name(provider["key"])
    credential_env = _variant_credential_env_for_create(state, provider)
    if credential_env and not provider.get("credentialOptional") and credential_env not in os.environ:
        state.message = f"Credential env {credential_env} is not set."
        return
    try:
        result, _output = _run_quiet(
            create_variant,
            name=name,
            provider_key=provider["key"],
            claude_version="latest",
            tweaks=state.selected_variant_tweaks,
            credential_env=credential_env,
            model_overrides=_variant_model_overrides_for_create(state),
            force=False,
        )
        setup_id = getattr(getattr(result, "variant", None), "variant_id", None) or variant_id_from_name(name)
        wrapper_path = getattr(result, "wrapper_path", None)
        config_path = workspace_root() / "variants" / setup_id / "variant.json"
        state.selected_setup_id = setup_id
        health = _run_setup_health(state, setup_id, show_result=False)
        state.last_action_summary = [
            "Setup created.",
            "",
            "Run it with:",
            f"  {Path(wrapper_path).name if wrapper_path else setup_id}",
            "",
            "Command:",
            f"  {wrapper_path or '(unknown)'}",
            "",
            "Config:",
            f"  {config_path}",
            "",
            f"Health: {health.get('status', 'unknown')}",
        ]
        state.message = f"Setup created: {wrapper_path or setup_id}"
        _reset_variant(state)
        message = state.message
        _set_mode(state, "health-result")
        state.message = message
    except Exception as exc:
        state.message = f"Setup create failed: {exc}"
