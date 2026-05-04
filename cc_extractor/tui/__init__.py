"""Interactive TUI for cc-extractor.

The action layer (mode dispatchers, build runners, key handlers, monkey-patch
re-exports) lives in this ``__init__`` module so test fixtures can do
``monkeypatch.setattr(tui, "create_variant", fake)`` and have the patch propagate
to internal call sites.

Pure helpers live in submodules (``state``, ``themes``, ``options``,
``rendering``, ``nav``, ``keys``, ``dashboard``, ``variant_actions``) and are
re-exported below to keep the existing ``tui._foo`` test API stable.
"""

import copy
import concurrent.futures
import os
import subprocess
import sys
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
    "delete_dashboard_tweak_profile", "delete_native_download", "delete_patch_profile", "extraction_paths",
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
    "_set_variant_provider_defaults", "_toggle_variant_mcp", "_toggle_variant_tweak",
    "_variant_credential_env_for_create", "_variant_model_overrides_for_create",
    "_run_inspect_delete", "_run_setup_health", "_run_setup_upgrade", "_run_setup_delete", "_route_startup",
    "_queue_setup_run", "_run_pending_setup",
    "_start_busy_action", "_poll_busy_action",
    "_load_saved_setup_list_preferences", "_save_setup_list_preferences",
    "_copy_logs", "_copy_setup_config", "_copy_text_to_clipboard", "_open_help", "_open_logs", "_open_variant_create_preview",
    "_event_requests_quit", "_screen_text", "_style", "_render_frame",
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
from ..variants.model import default_bin_dir, variant_id_from_name
from ..workspace import (
    DashboardTweakProfile,
    NativeArtifact,
    PatchPackage,
    PatchProfile,
    delete_dashboard_tweak_profile,
    delete_native_download,
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
    setup_provider_keys as _setup_provider_keys,
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
    toggle_variant_mcp as _toggle_variant_mcp,
    toggle_variant_tweak as _toggle_variant_tweak,
    variant_credential_env_for_create as _variant_credential_env_for_create,
    variant_model_overrides_for_create as _variant_model_overrides_for_create,
)


_BUSY_TICK_MS = 250
_BUSY_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="cc-extractor-tui",
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
    _load_saved_setup_list_preferences(state)
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
        if _event_requests_quit(event, KeyCode.Char):
            return False
        if app_state.mode == "busy":
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

    def on_tick(term, app_state):
        _poll_busy_action(app_state)

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
        on_tick=on_tick,
        on_start=on_start,
        on_stop=on_stop,
        tick_ms=_BUSY_TICK_MS,
        clear_each_frame=False,
    )
    app.run(state)
    if state.pending_run_command:
        code = _run_pending_setup(state)
        if code:
            raise SystemExit(code)


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


def _load_saved_setup_list_preferences(state):
    setup_list = load_tui_settings().get("setupList") or {}
    state.setup_search_text = str(setup_list.get("searchText") or "")
    state.setup_provider_filter = str(setup_list.get("providerFilter") or "all")
    sort_key = str(setup_list.get("sortKey") or "name")
    state.setup_sort_key = sort_key if sort_key in {"name", "provider", "health", "updated", "version"} else "name"
    state.setup_search_active = False


def _save_setup_list_preferences(state):
    settings = load_tui_settings()
    settings["themeId"] = settings.get("themeId") or state.theme_id
    settings["setupList"] = {
        "searchText": state.setup_search_text,
        "providerFilter": state.setup_provider_filter,
        "sortKey": state.setup_sort_key,
    }
    try:
        save_tui_settings(settings)
        return True
    except Exception as exc:
        state.message = f"Setup list preferences changed but save failed: {exc}"
        return False


def _log_lines(output, fallback="No backend output captured."):
    lines = str(output or "").splitlines()
    return lines if lines else [fallback]


def _stage_log_lines(*stages):
    if stages and all(isinstance(stage, tuple) and len(stage) == 2 for stage in stages):
        pairs = stages
    else:
        pairs = list(zip(stages[0::2], stages[1::2]))
    lines = []
    for label, output in pairs:
        lines.append(f"[{label}]")
        lines.extend(_log_lines(output))
    return lines or ["No backend output captured."]


def _build_stage_lines(stages):
    lines = []
    for stage in stages or []:
        name = getattr(stage, "name", None) or str(getattr(stage, "get", lambda _key, default=None: default)("name", "stage"))
        status = getattr(stage, "status", None) or str(getattr(stage, "get", lambda _key, default=None: default)("status", "unknown"))
        detail = getattr(stage, "detail", None) or getattr(stage, "get", lambda _key, default=None: default)("detail", "")
        line = f"{name}: {status}"
        if detail:
            line = f"{line} ({detail})"
        lines.append(line)
    return lines


def _exception_stage_lines(exc):
    return _build_stage_lines(getattr(exc, "stages", []))


def _result_stage_lines(results):
    lines = []
    for result in results or []:
        lines.extend(_build_stage_lines(getattr(result, "stages", [])))
    return lines


def _append_backend_stages(summary, stage_lines):
    if stage_lines:
        summary.extend(["", "Backend stages:", *stage_lines])
    return summary


def _stage_lines_from_log(log_lines):
    if "[Build stages]" not in (log_lines or []):
        return []
    index = log_lines.index("[Build stages]")
    return list(log_lines[index + 1:])


def _copy_text_to_clipboard(text):
    subprocess.run(["pbcopy"], input=str(text), text=True, check=True)


# -- Busy action helpers ------------------------------------------------------

def _clear_busy_state(state):
    state.busy_title = ""
    state.busy_detail = ""
    state.busy_ticks = 0
    state.busy_future = None


def _copy_completed_busy_state(state, completed_state):
    state.__dict__.clear()
    state.__dict__.update(copy.deepcopy(completed_state.__dict__))
    _clear_busy_state(state)


def _run_busy_action(worker_state, action):
    _clear_busy_state(worker_state)
    action(worker_state)
    return worker_state


def _start_busy_action(state, title, detail, action):
    if state.busy_future is not None:
        state.message = "Already working. Input is locked while this runs."
        return False
    worker_state = copy.deepcopy(state)
    future = _BUSY_EXECUTOR.submit(_run_busy_action, worker_state, action)
    state.busy_title = str(title)
    state.busy_detail = str(detail)
    state.busy_ticks = 0
    state.busy_future = future
    state.message = f"{title}..."
    _set_mode(state, "busy")
    state.message = f"{title}..."
    return True


def _poll_busy_action(state):
    if state.mode != "busy" or state.busy_future is None:
        return False
    state.busy_ticks += 1
    if not state.busy_future.done():
        return False
    future = state.busy_future
    try:
        completed_state = future.result()
    except Exception as exc:
        _clear_busy_state(state)
        state.last_action_log = _stage_log_lines("Busy action failure", str(exc))
        state.last_action_summary = [f"Action failed: {exc}"]
        state.message = f"Action failed: {exc}"
        _set_mode(state, "error")
        state.message = f"Action failed: {exc}"
        return True
    _copy_completed_busy_state(state, completed_state)
    return True


def _busy_create_action(worker_state):
    _run_variant_create(worker_state)
    _refresh_state(worker_state)


def _busy_upgrade_action(worker_state):
    _run_setup_upgrade(worker_state)


def _busy_tweak_apply_action(worker_state):
    _run_tweak_apply(worker_state)
    _refresh_state(worker_state)


# -- Key handlers ------------------------------------------------------------

def _event_requests_quit(event, char_key_code):
    if event.get("kind") != "key":
        return False

    key_name = str(event.get("key") or event.get("name") or "").replace("-", "+").lower()
    if key_name in {"ctrl+c", "control+c"}:
        return True

    code = event.get("code")
    code_name = str(code).lower()
    code_is_char = code == int(char_key_code) or code_name == "char"
    if not code_is_char:
        return False

    ch = event.get("ch")
    if ch in {3, "\x03"}:
        return True

    if isinstance(ch, int):
        char = chr(ch) if 0 <= ch <= 0x10FFFF else ""
    else:
        char = str(ch or "")

    modifiers = event.get("modifiers") or event.get("mods") or event.get("modifier") or ""
    if isinstance(modifiers, (list, tuple, set)):
        modifier_text = " ".join(str(modifier).lower() for modifier in modifiers)
    else:
        modifier_text = str(modifiers).lower()
    has_control = "ctrl" in modifier_text or "control" in modifier_text
    return has_control and char.lower() == "c"


def _handle_backspace_key(state):
    if state.mode == "busy":
        return True
    if state.mode == "setup-manager" and state.setup_search_active:
        state.setup_search_text = state.setup_search_text[:-1]
        _clamp_setup_manager_selection(state)
        state.message = f"Search: {state.setup_search_text or 'none'}"
        _save_setup_list_preferences(state)
        return True
    if state.mode in {"tweaks-edit", "tweak-editor"} and state.tweak_search_active:
        state.tweak_search = state.tweak_search[:-1]
        state.selected_index = state._clamp(state.selected_index, state.item_count())
        state.message = f"Tweak search: {state.tweak_search or 'none'}"
        return True
    if state.mode == "delete-confirm":
        state.delete_confirm_text = state.delete_confirm_text[:-1]
        return True
    if state.mode == "dashboard":
        return _dashboard_backspace(state)
    if state.mode in {"variants", "first-run-setup"}:
        return _variant_backspace(state)
    return False


def _handle_char_key(state, char):
    if char == "\x03":
        return False
    if state.mode == "busy":
        return True

    if state.mode == "delete-confirm":
        if char.isprintable() and char not in "\r\n\t":
            state.delete_confirm_text += char
        return True

    if state.mode == "inspect-delete-confirm":
        if char.lower() == "y":
            _run_inspect_delete(state)
        elif char.lower() == "n":
            _cancel_inspect_delete(state)
        else:
            state.message = "Press y to delete, or n/Esc to cancel."
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

    if state.mode == "setup-manager" and state.setup_search_active:
        if char.isprintable() and char not in "\r\n\t":
            state.setup_search_text += char
            _clamp_setup_manager_selection(state)
            state.message = f"Search: {state.setup_search_text}"
            _save_setup_list_preferences(state)
        return True

    if state.mode in {"tweaks-edit", "tweak-editor"} and state.tweak_search_active:
        if char.isprintable() and char not in "\r\n\t":
            state.tweak_search += char
            state.selected_index = state._clamp(state.selected_index, state.item_count())
            state.message = f"Tweak search: {state.tweak_search}"
        return True

    lowered = char.lower()
    if lowered == "q":
        return False
    if char == "?":
        _open_help(state)
        return True
    if state.mode == "upgrade-preview":
        if lowered == "y":
            _start_busy_action(
                state,
                "Upgrading setup",
                f"Rebuilding setup {state.selected_setup_id or 'selected setup'}",
                _busy_upgrade_action,
            )
        elif lowered == "n":
            _go_back(state)
        return True
    if state.mode == "create-preview":
        if lowered == "y":
            name = state.variant_name.strip() or "new setup"
            _start_busy_action(
                state,
                "Creating setup",
                f"Building custom Claude setup {name}",
                _busy_create_action,
            )
        elif lowered == "n":
            _go_back(state)
        return True
    if state.mode in {"tweaks-edit", "tweak-editor"} and state.tweak_apply_preview:
        if lowered == "y":
            _start_busy_action(
                state,
                "Rebuilding tweaks",
                f"Applying tweak changes to setup {state.tweaks_variant_id or 'selected setup'}",
                _busy_tweak_apply_action,
            )
        elif lowered == "n":
            state.tweak_apply_preview = False
            state.message = "Tweak rebuild cancelled."
        return True
    handled_setup_key = False
    if char == "/" and state.mode == "setup-manager":
        state.setup_search_active = True
        state.message = "Search setups."
        handled_setup_key = True
    elif char == "/" and state.mode in {"tweaks-edit", "tweak-editor"}:
        state.tweak_search_active = True
        state.message = "Search tweaks."
        return True
    elif lowered == "p" and state.mode == "setup-manager":
        _cycle_setup_provider_filter(state)
        handled_setup_key = True
    elif lowered == "s" and state.mode == "setup-manager":
        _cycle_setup_sort(state)
        handled_setup_key = True
    elif lowered == "n" and state.mode in {"setup-manager", "setup-detail", "health-result"}:
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
    elif lowered == "x" and state.mode in {"setup-manager", "setup-detail"}:
        setup_id = _current_setup_id_for_action(state)
        if setup_id:
            _queue_setup_run(state, setup_id)
        handled_setup_key = True
    elif lowered == "t" and state.mode in {"setup-manager", "setup-detail"}:
        _open_tweak_editor(state)
        handled_setup_key = True
    elif lowered == "r" and state.mode == "setup-manager":
        _refresh_state(state)
        state.message = "Setup list refreshed."
        handled_setup_key = True
    elif lowered == "c" and state.mode == "setup-detail":
        _copy_setup_command(state)
        handled_setup_key = True
    elif lowered == "g" and state.mode == "setup-detail":
        _copy_setup_config(state)
        handled_setup_key = True
    elif lowered == "c" and state.mode in {"health-result", "logs"}:
        _copy_logs(state)
        handled_setup_key = True
    elif lowered == "l" and state.mode in {"setup-detail", "health-result"}:
        _open_logs(state)
        handled_setup_key = True
    if handled_setup_key:
        return not state.pending_run_command
    if lowered == "b":
        _go_back(state)
    elif lowered == "t":
        if state.mode not in {"setup-manager", "setup-detail"}:
            _cycle_theme(state)
    elif lowered == "a" and state.mode in {"tweaks-edit", "tweak-editor"}:
        _begin_tweak_apply_preview(state)
    elif lowered == "d" and state.mode in {"tweaks-edit", "tweak-editor"}:
        _discard_tweaks(state)
    elif lowered == "d" and state.mode == "inspect":
        _open_inspect_delete_confirm(state)
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
        elif option and option.kind == "variant-mcp":
            _toggle_variant_mcp(state, str(option.value))
    elif state.mode in {"tweaks-edit", "tweak-editor"}:
        _toggle_tweak(state)


# -- Activate dispatchers ----------------------------------------------------

def _activate(state):
    state.message = ""
    if state.mode == "setup-manager" and state.setup_search_active:
        state.setup_search_active = False
        state.message = f"Search filter kept: {state.setup_search_text or 'none'}"
        return True
    if state.mode in {"tweaks-edit", "tweak-editor"} and state.tweak_search_active:
        state.tweak_search_active = False
        state.message = f"Tweak search kept: {state.tweak_search or 'none'}"
        return True
    if state.mode == "busy":
        return True
    try:
        if state.mode == "setup-manager":
            _activate_setup_manager(state)
        elif state.mode == "setup-detail":
            _activate_setup_detail(state)
        elif state.mode == "first-run-setup":
            _activate_variants(state)
        elif state.mode == "create-preview":
            state.message = "Press y to create this setup, or n/Esc to cancel."
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
        elif state.mode == "inspect-delete-confirm":
            state.message = "Press y to delete, or n/Esc to cancel."
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
    return not state.pending_run_command


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
    elif option.kind == "setup-action-run" and setup_id:
        _queue_setup_run(state, setup_id)
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


def _open_inspect_delete_confirm(state):
    artifact = _selected_artifact(state)
    if artifact is None:
        return
    state.inspect_delete_confirm_path = str(artifact.path)
    _set_mode(state, "inspect-delete-confirm")
    state.message = "Confirm deleting this downloaded native artifact."


def _cancel_inspect_delete(state):
    state.inspect_delete_confirm_path = ""
    _set_mode(state, "inspect")
    state.message = "Delete cancelled."


def _open_tweak_editor(state):
    setup_id = _current_setup_id_for_action(state)
    if setup_id is None:
        return
    _enter_tweaks_for_variant(state, setup_id)


def _open_variant_create_preview(state):
    provider = _selected_variant_provider(state)
    if provider is None:
        state.message = "Select a provider first."
        return
    if not state.variant_name.strip():
        state.message = "Type a setup name first."
        return
    state.last_action_summary = []
    _set_mode(state, "create-preview")


def _copy_setup_command(state):
    variant = _selected_setup_variant(state)
    if variant is None:
        state.message = "Select a setup first."
        return
    wrapper = ((variant.manifest or {}).get("paths") or {}).get("wrapper") or ""
    if not wrapper:
        state.message = f"Setup {variant.variant_id} has no command path to copy."
        return
    try:
        _copy_text_to_clipboard(wrapper)
    except Exception as exc:
        state.message = f"Copy failed: {exc}"
        return
    state.last_action_log = [f"Copied command path: {wrapper}"]
    state.message = f"Copied command path for setup {variant.variant_id}."


def _copy_setup_config(state):
    variant = _selected_setup_variant(state)
    if variant is None:
        state.message = "Select a setup first."
        return
    config_path = variant.path / "variant.json"
    try:
        _copy_text_to_clipboard(str(config_path))
    except Exception as exc:
        state.message = f"Copy failed: {exc}"
        return
    state.last_action_log = [f"Copied setup config path: {config_path}"]
    state.message = f"Copied setup config path for setup {variant.variant_id}."


def _queue_setup_run(state, setup_id):
    variant = next((item for item in state.variants if item.variant_id == setup_id), None)
    if variant is None:
        state.message = f"Setup {setup_id} not found."
        return
    wrapper_path = default_bin_dir() / setup_id
    if not wrapper_path.is_file():
        state.message = f"Setup command is missing: {wrapper_path}"
        return
    state.selected_setup_id = setup_id
    state.pending_run_setup_id = setup_id
    state.pending_run_command = [str(wrapper_path)]
    state.last_action_log = [f"Queued setup run: {wrapper_path}"]
    state.message = f"Running setup {setup_id} after setup manager exits."


def _clear_terminal_for_external_command():
    if not sys.stdout.isatty():
        return
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def _run_pending_setup(state):
    command = list(state.pending_run_command or [])
    if not command:
        return 0
    setup_id = state.pending_run_setup_id or Path(command[0]).name
    _clear_terminal_for_external_command()
    print(f"Running setup {setup_id}: {command[0]}")
    try:
        result = subprocess.run(command, check=False)
    except KeyboardInterrupt:
        return 130
    return result.returncode


def _copy_logs(state):
    text = "\n".join(state.last_action_log or state.last_action_summary or ["No logs available."])
    try:
        _copy_text_to_clipboard(text)
    except Exception as exc:
        state.message = f"Copy failed: {exc}"
        return
    state.message = "Copied log text."


def _open_logs(state):
    if not state.last_action_log:
        state.last_action_log = ["No logs available."]
    _set_mode(state, "logs")


def _open_help(state):
    state.help_return_mode = state.mode if state.mode != "help" else (state.help_return_mode or "setup-manager")
    _set_mode(state, "help")


def _health_status_from_report(report):
    return "healthy" if report and report.get("ok") else "broken"


def _yes_no(value):
    return "yes" if value else "no"


def _path_snapshot(path):
    if not path:
        return {"path": "", "exists": False, "size": None, "mtime_ns": None}
    path = Path(path)
    try:
        stat = path.stat()
    except OSError:
        return {"path": str(path), "exists": False, "size": None, "mtime_ns": None}
    return {
        "path": str(path),
        "exists": True,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _path_changed(before, after):
    return (
        before.get("exists") != after.get("exists")
        or before.get("size") != after.get("size")
        or before.get("mtime_ns") != after.get("mtime_ns")
    )


def _expected_setup_snapshot(setup_id):
    setup_dir = workspace_root() / "variants" / setup_id
    wrapper = workspace_root() / "bin" / setup_id
    config = setup_dir / "variant.json"
    return {
        "setup_dir": _path_snapshot(setup_dir),
        "wrapper": _path_snapshot(wrapper),
        "config": _path_snapshot(config),
    }


def _variant_setup_snapshot(variant):
    manifest = variant.manifest or {}
    paths = manifest.get("paths") or {}
    wrapper = paths.get("wrapper") or ""
    binary = paths.get("binary") or ""
    return {
        "manifest": dict(manifest),
        "setup_dir": _path_snapshot(variant.path),
        "wrapper": _path_snapshot(wrapper),
        "binary": _path_snapshot(binary),
        "config": _path_snapshot(variant.path / "variant.json"),
    }


def _create_failure_summary(setup_id, before, exc):
    after = _expected_setup_snapshot(setup_id)
    setup_created = not before["setup_dir"]["exists"] and after["setup_dir"]["exists"]
    command_created = not before["wrapper"]["exists"] and after["wrapper"]["exists"]
    config_created = not before["config"]["exists"] and after["config"]["exists"]
    changed = any(_path_changed(before[key], after[key]) for key in ("setup_dir", "wrapper", "config"))
    cleanup_needed = setup_created or command_created or config_created
    return [
        "Create failed.",
        f"Setup: {setup_id}",
        f"Setup directory created: {_yes_no(setup_created)}",
        f"Command created: {_yes_no(command_created)}",
        f"Setup config created: {_yes_no(config_created)}",
        f"Previous state changed: {_yes_no(changed)}",
        f"Cleanup needed: {_yes_no(cleanup_needed)}",
        f"Failed stage: create setup: {exc}",
    ]


def _target_version_for_summary(state, target):
    if target == "latest":
        return str((state.download_index.get("binary") or {}).get("latest") or "")
    return str(target or "")


def _has_cached_native_artifact(state, version):
    if not version:
        return False
    return any(getattr(artifact, "version", None) == version for artifact in state.native_artifacts)


def _base_download_status(state, target_version, cached_before):
    if not target_version:
        return "unknown"
    if cached_before:
        return "already cached"
    if _has_cached_native_artifact(state, target_version):
        return "verified"
    return "not found"


def _post_variant_snapshot(setup_id, fallback):
    try:
        variant = load_variant(setup_id)
    except Exception:
        return None, fallback
    return variant, _variant_setup_snapshot(variant)


def _command_replaced_status(before, after):
    if not before.get("path") or not after.get("path"):
        return "unknown"
    if not after.get("exists"):
        return "unknown, command missing"
    return "yes" if _path_changed(before, after) else "no"


def _active_setup_status(snapshot):
    if snapshot is None:
        return "unknown"
    wrapper_exists = snapshot["wrapper"]["exists"]
    binary_exists = snapshot["binary"]["exists"]
    return "yes" if wrapper_exists and binary_exists else "no"


def _run_setup_health(state, setup_id, *, show_result=False):
    try:
        reports, output = _run_quiet(doctor_variant, setup_id)
        report = reports[0] if reports else {"id": setup_id, "ok": False, "checks": []}
        status = _health_status_from_report(report)
        checks = report.get("checks", []) or []
        state.setup_health[setup_id] = {
            "status": status,
            "checks": checks,
            "message": f"Health: {status}",
            "output": output,
        }
        state.last_action_log = _stage_log_lines("Health", output)
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
            "output": str(exc),
        }
        state.last_action_log = _stage_log_lines("Health", str(exc))
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
    before = _variant_setup_snapshot(variant)
    target_version = _target_version_for_summary(state, target)
    cached_before = _has_cached_native_artifact(state, target_version)
    try:
        results, update_output = _run_quiet(update_variants, setup_id, claude_version=target)
        _refresh_state(state)
        state.selected_setup_id = setup_id
        refreshed = _selected_setup_variant(state)
        new_version = ((refreshed.manifest or {}).get("source") or {}).get("version") if refreshed else "?"
        health = _run_setup_health(state, setup_id, show_result=False)
        stage_lines = _result_stage_lines(results)
        state.last_action_log = _stage_log_lines(
            "Upgrade",
            update_output,
            "Build stages",
            "\n".join(stage_lines),
            "Health",
            health.get("output", ""),
        )
        wrapper = ""
        if results:
            wrapper = str(getattr(results[0], "wrapper_path", "") or "")
        if not wrapper and refreshed is not None:
            wrapper = str(((refreshed.manifest or {}).get("paths") or {}).get("wrapper") or "")
        status = health.get("status", "unknown")
        state.last_action_summary = _append_backend_stages([
            f"Setup upgraded: {setup_id}",
            f"Claude Code: {old_version} -> {new_version or target}",
            "Tweaks reapplied: yes",
            f"Command rebuilt path: {wrapper or '(unknown)'}",
            f"Health: {status}",
        ], stage_lines)
        state.message = f"Upgrade complete for setup {setup_id}: {status}"
    except Exception as exc:
        refresh_message = ""
        try:
            _refresh_state(state)
            state.selected_setup_id = setup_id
        except Exception as refresh_exc:
            refresh_message = f" Refresh failed after error: {refresh_exc}"
        post_variant, after = _post_variant_snapshot(setup_id, before)
        base_status = _base_download_status(state, target_version, cached_before)
        command_replaced = _command_replaced_status(before["wrapper"], after["wrapper"])
        active = "unknown" if post_variant is None else _active_setup_status(after)
        stage_lines = _exception_stage_lines(exc)
        state.last_action_log = _stage_log_lines(
            "Upgrade failure",
            str(exc),
            "Build stages",
            "\n".join(stage_lines),
        )
        state.last_action_summary = _append_backend_stages([
            f"Upgrade failed: {setup_id}",
            f"Claude Code: {old_version} -> {target}",
            f"Base download succeeded: {base_status}",
            f"Command replaced: {command_replaced}",
            f"Previous setup remains active: {active}",
            f"Failed stage: update/rebuild: {exc}",
        ], stage_lines)
        if refresh_message:
            state.last_action_summary.append(refresh_message.strip())
        state.message = f"Upgrade failed: {exc}"
    message = state.message
    _set_mode(state, "health-result")
    state.message = message


def _inspect_delete_artifact(state):
    target = state.inspect_delete_confirm_path
    if not target:
        return None
    for artifact in state.native_artifacts:
        if str(artifact.path) == target:
            return artifact
    return None


def _run_inspect_delete(state):
    artifact = _inspect_delete_artifact(state)
    if artifact is None:
        state.inspect_delete_confirm_path = ""
        _set_mode(state, "inspect")
        state.message = "Selected native artifact is no longer available."
        return

    label = f"{artifact.version} {artifact.platform} {short_sha(artifact.sha256)}"
    try:
        removed = delete_native_download(artifact)
    except Exception as exc:
        state.last_action_log = _stage_log_lines("Native artifact delete failure", str(exc))
        _set_mode(state, "inspect")
        state.message = f"Delete failed: {exc}"
        return

    state.inspect_delete_confirm_path = ""
    _refresh_state(state)
    state.message = f"Deleted native artifact: {label}" if removed else f"Native artifact already missing: {label}"
    _set_mode(state, "inspect")
    state.message = f"Deleted native artifact: {label}" if removed else f"Native artifact already missing: {label}"


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
    delete_failed = False
    removed = False
    try:
        removed, output = _run_quiet(remove_variant, setup_id, yes=True)
        setup_removed = not setup_dir.exists()
        command_removed = True if wrapper_path is None else not wrapper_path.exists()
        state.last_action_log = _stage_log_lines("Delete", output)
        state.message = f"Deleted setup {setup_id}." if removed else f"Setup {setup_id} was not found."
    except Exception as exc:
        delete_failed = True
        setup_removed = not setup_dir.exists()
        command_removed = True if wrapper_path is None else not wrapper_path.exists()
        state.last_action_log = _stage_log_lines("Delete failure", str(exc))
        state.message = f"Delete failed: {exc}"
    title = f"Deleted setup: {setup_id}"
    if delete_failed:
        title = f"Delete failed: {setup_id}"
    elif not removed:
        title = f"Setup not found: {setup_id}"
    state.last_action_summary = [
        title,
        f"Setup directory removed: {'yes' if setup_removed else 'no'}",
        f"Command removed: {'yes' if command_removed else 'no'}",
        "Shared downloads untouched: yes",
        "Next: fix the reported issue, refresh setup list, or retry delete.",
    ]
    state.delete_confirm_text = ""
    _refresh_state(state)
    if setup_removed:
        state.selected_setup_id = None
    else:
        state.selected_setup_id = setup_id
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
    rebuild_log = list(state.last_action_log)
    if not state.message.startswith("Applied tweaks"):
        state.last_action_summary = _append_backend_stages([state.message], _stage_lines_from_log(rebuild_log))
        message = state.message
        _set_mode(state, "health-result")
        state.message = message
        return
    state.selected_setup_id = setup_id
    health = _run_setup_health(state, setup_id, show_result=False)
    state.last_action_log = _stage_log_lines(
        "Tweak rebuild",
        "\n".join(rebuild_log),
        "Health",
        health.get("output", ""),
    )
    state.last_tweak_result = {
        "added": added,
        "removed": removed,
        "health": health.get("status", "unknown"),
    }
    state.last_action_summary = _append_backend_stages([
        "Tweaks updated:",
        f"Added: {', '.join(added) if added else 'none'}",
        f"Removed: {', '.join(removed) if removed else 'none'}",
        "Rebuild: successful",
        f"Health: {health.get('status', 'unknown')}",
    ], _stage_lines_from_log(rebuild_log))
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


def _cycle_setup_provider_filter(state):
    options = ["all", *_setup_provider_keys(state)]
    current = state.setup_provider_filter if state.setup_provider_filter in options else "all"
    state.setup_provider_filter = options[(options.index(current) + 1) % len(options)]
    state.selected_index = 0
    state.message = f"Provider filter: {state.setup_provider_filter}"
    _save_setup_list_preferences(state)


def _cycle_setup_sort(state):
    order = ["name", "provider", "health", "updated", "version"]
    current = state.setup_sort_key if state.setup_sort_key in order else "name"
    state.setup_sort_key = order[(order.index(current) + 1) % len(order)]
    state.selected_index = 0
    state.message = f"Setup sort: {state.setup_sort_key}"
    _save_setup_list_preferences(state)


def _clamp_setup_manager_selection(state):
    count = state.item_count()
    if count < 1:
        state.selected_index = 0
    else:
        state.selected_index = max(0, min(state.selected_index, count - 1))


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
        state.variant_step = 3
        state.selected_index = 0
    elif option.kind == "variant-mcp":
        _toggle_variant_mcp(state, str(option.value))
    elif option.kind == "variant-mcp-continue":
        provider = _selected_variant_provider(state)
        if provider and not provider.get("requiresModelMapping"):
            state.variant_step = 5
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
        _open_variant_create_preview(state)
    elif option.kind == "variant-review-back":
        state.variant_step = 5
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
        expected_setup_id = variant_id_from_name(name)
    except Exception as exc:
        state.last_action_log = _stage_log_lines("Create failure", str(exc))
        state.last_action_summary = [
            "Create failed.",
            f"Setup: {name}",
            "Setup directory created: no",
            "Command created: no",
            "Setup config created: no",
            "Previous state changed: no",
            "Cleanup needed: no",
            f"Failed stage: validate setup id: {exc}",
        ]
        state.message = f"Setup create failed: {exc}"
        message = state.message
        _set_mode(state, "error")
        state.message = message
        return
    before = _expected_setup_snapshot(expected_setup_id)
    try:
        result, output = _run_quiet(
            create_variant,
            name=name,
            provider_key=provider["key"],
            claude_version="latest",
            tweaks=state.selected_variant_tweaks,
            credential_env=credential_env,
            model_overrides=_variant_model_overrides_for_create(state),
            mcp_ids=state.selected_variant_mcp_ids,
            force=False,
        )
        state.last_action_log = _stage_log_lines("Create setup", output)
        stage_lines = _build_stage_lines(getattr(result, "stages", []))
        setup_id = getattr(getattr(result, "variant", None), "variant_id", None) or variant_id_from_name(name)
        wrapper_path = getattr(result, "wrapper_path", None)
        config_path = workspace_root() / "variants" / setup_id / "variant.json"
        state.selected_setup_id = setup_id
        health = _run_setup_health(state, setup_id, show_result=False)
        state.last_action_log = _stage_log_lines(
            "Create setup",
            output,
            "Build stages",
            "\n".join(stage_lines),
            "Health",
            health.get("output", ""),
        )
        state.last_action_summary = _append_backend_stages([
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
        ], stage_lines)
        state.message = f"Setup created: {wrapper_path or setup_id}"
        _reset_variant(state)
        message = state.message
        _set_mode(state, "health-result")
        state.message = message
    except Exception as exc:
        stage_lines = _exception_stage_lines(exc)
        state.last_action_log = _stage_log_lines(
            "Create failure",
            str(exc),
            "Build stages",
            "\n".join(stage_lines),
        )
        state.last_action_summary = _append_backend_stages(
            _create_failure_summary(expected_setup_id, before, exc),
            stage_lines,
        )
        state.message = f"Setup create failed: {exc}"
        message = state.message
        _set_mode(state, "error")
        state.message = message
