"""Interactive TUI for cc-extractor.

The action layer (mode dispatchers, build runners, key handlers, monkey-patch
re-exports) lives in this ``__init__`` module so test fixtures can do
``monkeypatch.setattr(tui, "create_variant", fake)`` and have the patch propagate
to internal call sites.

Pure helpers live in submodules (``state``, ``themes``, ``options``,
``rendering``, ``nav``, ``keys``, ``dashboard``, ``variant_actions``) and are
re-exported below to keep the existing ``tui._foo`` test API stable.
"""

# Externally-supplied helpers that tests monkey-patch through ``tui.<name>``.
# Imports must stay in this module so internal callers resolve through the
# package globals that ``monkeypatch.setattr`` updates.
from ..bun_extract import parse_bun_binary
from ..download_index import download_versions, load_download_index, refresh_download_index
from ..downloader import download_binary
from ..extractor import extract_all
from ..patch_workflow import apply_patch_packages_to_native
from ..providers import provider_default_variant_name
from ..variant_tweaks import CURATED_TWEAK_IDS, DEFAULT_TWEAK_IDS
from ..variants import create_variant, doctor_variant, list_variant_providers, scan_variants
from ..workspace import (
    NativeArtifact,
    PatchPackage,
    PatchProfile,
    delete_patch_profile,
    extraction_paths,
    load_patch_profile,
    load_tui_settings,
    native_artifact_from_path,
    rename_patch_profile,
    save_patch_profile,
    save_tui_settings,
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
    go_back as _go_back,
    move_tab as _move_tab,
    selected_artifact as _selected_artifact,
    set_mode as _set_mode,
    source_artifact as _source_artifact,
    toggle_patch as _toggle_patch,
)
from .options import (
    dashboard_options as _dashboard_options,
    dashboard_source_artifact as _dashboard_source_artifact,
    loaded_profile as _loaded_profile,
    profile_by_id as _profile_by_id,
    profile_missing_refs as _profile_missing_refs,
    profile_refs_by_key as _profile_refs_by_key,
    selected_dashboard_option as _selected_dashboard_option,
    selected_dashboard_packages as _selected_dashboard_packages,
    selected_patch_refs as _selected_patch_refs,
    selected_variant_option as _selected_variant_option,
    selected_variant_provider as _selected_variant_provider,
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
    _refresh_state(state)

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


# -- Key handlers ------------------------------------------------------------

def _handle_backspace_key(state):
    if state.mode == "dashboard":
        return _dashboard_backspace(state)
    if state.mode == "variants":
        return _variant_backspace(state)
    return False


def _handle_char_key(state, char):
    if state.mode == "dashboard" and _dashboard_accepts_profile_text(state):
        if char.isprintable() and char not in "\r\n\t":
            state.dashboard_profile_name += char
            state.dashboard_delete_confirm_id = ""
        return True

    if state.mode == "variants" and _variant_accepts_text(state):
        if char.isprintable() and char not in "\r\n\t":
            _variant_append_text(state, char)
        return True

    lowered = char.lower()
    if lowered == "q":
        return False
    if lowered == "b":
        _go_back(state)
    elif lowered == "t":
        _cycle_theme(state)
    elif char == " ":
        _toggle_selected(state)
    elif lowered == "r" and state.mode == "dashboard" and state.dashboard_step == 0:
        _refresh_dashboard_index(state)

    return True


def _variant_accepts_name_text(state):
    if state.mode != "variants" or state.variant_step != 1:
        return False
    option = _selected_variant_option(state)
    return option is not None and option.kind == "variant-name"


def _toggle_selected(state):
    if state.mode == "dashboard":
        option = _selected_dashboard_option(state)
        if option and option.kind == "patch-toggle":
            _toggle_dashboard_patch(state, int(option.value))
    elif state.mode == "patch-package":
        _toggle_patch(state)
    elif state.mode == "variants":
        option = _selected_variant_option(state)
        if option and option.kind == "variant-tweak":
            _toggle_variant_tweak(state, str(option.value))


# -- Activate dispatchers ----------------------------------------------------

def _activate(state):
    state.message = ""
    try:
        if state.mode == "dashboard":
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
    except Exception as exc:
        state.message = f"Action failed: {exc}"

    _refresh_state(state)
    return True


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
    elif option.kind == "patch-toggle":
        _toggle_dashboard_patch(state, int(option.value))
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
            state.message = f"Variant {option.value}: {'ok' if ok else 'failed'}"
        except Exception as exc:
            state.message = f"Variant status failed: {exc}"
    elif option.kind == "variant-provider":
        state.variant_provider_index = int(option.value)
        provider = _selected_variant_provider(state)
        _set_variant_provider_defaults(state, provider)
        _advance_variant(state)
    elif option.kind == "variant-name":
        state.message = "Type a variant name here, then continue."
    elif option.kind == "variant-name-continue":
        if not state.variant_name.strip():
            state.message = "Type a variant name first."
            return
        _advance_variant(state)
    elif option.kind == "variant-credential-env":
        state.message = "Type a credential environment variable name. Raw API keys are not accepted here."
    elif option.kind == "variant-credentials-continue":
        _advance_variant(state)
    elif option.kind == "variant-model":
        state.message = f"Type the {option.value} model alias, or clear it to use the provider default."
    elif option.kind == "variant-models-continue":
        if _require_variant_model_mapping(state):
            _advance_variant(state)
    elif option.kind == "variant-tweak":
        _toggle_variant_tweak(state, str(option.value))
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
        missing = _profile_missing_refs(state, loaded_profile)
        if missing:
            state.message = f"Loaded profile is invalid, missing {', '.join(missing)}"
            return

    packages = _selected_dashboard_packages(state)
    try:
        artifact = _dashboard_artifact_for_run(state)
        if artifact is None:
            return
        result, _output = _run_quiet(apply_patch_packages_to_native, artifact, packages)
        state.message = f"Dashboard build complete: {result.output_path}"
    except Exception as exc:
        state.message = f"Dashboard build failed: {exc}"


def _run_variant_create(state):
    provider = _selected_variant_provider(state)
    if provider is None:
        state.message = "Select a provider first."
        return
    name = state.variant_name.strip() or provider_default_variant_name(provider["key"])
    try:
        result, _output = _run_quiet(
            create_variant,
            name=name,
            provider_key=provider["key"],
            claude_version="latest",
            tweaks=state.selected_variant_tweaks,
            credential_env=_variant_credential_env_for_create(state, provider),
            model_overrides=_variant_model_overrides_for_create(state),
            force=False,
        )
        state.message = f"Variant created: {result.wrapper_path}"
        _reset_variant(state)
    except Exception as exc:
        state.message = f"Variant create failed: {exc}"
