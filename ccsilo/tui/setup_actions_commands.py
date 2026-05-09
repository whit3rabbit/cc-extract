"""Command, clipboard, and log navigation actions for the TUI."""

from pathlib import Path

from .setup_actions_common import (  # noqa: F401
    _active_setup_status,
    _append_backend_stages,
    _base_download_status,
    _build_stage_lines,
    _command_replaced_status,
    _copy_text_to_clipboard,
    _create_failure_summary,
    _exception_stage_lines,
    _expected_setup_snapshot,
    _has_cached_native_artifact,
    _health_status_from_report,
    _log_lines,
    _managed_install_paths,
    _models_pending_diff,
    _path_changed,
    _path_snapshot,
    _post_variant_snapshot,
    _result_stage_lines,
    _run_quiet,
    _stage_lines_from_log,
    _stage_log_lines,
    _target_version_for_summary,
    _tui,
    _variant_setup_snapshot,
    _yes_no,
    apply_dashboard_tweaks_to_native,
    create_variant,
    default_bin_dir,
    delete_native_download,
    doctor_variant,
    download_versions,
    fetch_provider_models,
    inspect_variant_command_install,
    install_variant_command,
    load_tui_settings,
    load_variant,
    provider_default_variant_name,
    refresh_download_index,
    remove_variant,
    run_ccrouter_command,
    save_tui_settings,
    short_sha,
    stored_credential_value,
    update_variant_models,
    update_variants,
    variant_id_from_name,
    variant_install_cleanup_paths,
    workspace_root,
)


__all__ = [
    "_copy_setup_command",
    "_copy_setup_config",
    "_queue_setup_run",
    "_clear_terminal_for_external_command",
    "_run_pending_setup",
    "_copy_logs",
    "_open_logs",
    "_open_help",
]

def _copy_setup_command(state):
    variant = _tui()._selected_setup_variant(state)
    if variant is None:
        state.message = "Select a setup first."
        return
    wrapper = ((variant.manifest or {}).get("paths") or {}).get("wrapper") or ""
    if not wrapper:
        state.message = f"Setup {variant.variant_id} has no command path to copy."
        return
    try:
        _tui()._copy_text_to_clipboard(wrapper)
    except Exception as exc:
        state.message = f"Copy failed: {exc}"
        return
    state.last_action_log = [f"Copied command path: {wrapper}"]
    state.message = f"Copied command path for setup {variant.variant_id}."

def _copy_setup_config(state):
    variant = _tui()._selected_setup_variant(state)
    if variant is None:
        state.message = "Select a setup first."
        return
    config_path = variant.path / "variant.json"
    try:
        _tui()._copy_text_to_clipboard(str(config_path))
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
    if not _tui().sys.stdout.isatty():
        return
    _tui().sys.stdout.write("\033[2J\033[H")
    _tui().sys.stdout.flush()

def _run_pending_setup(state):
    command = list(state.pending_run_command or [])
    if not command:
        return 0
    setup_id = state.pending_run_setup_id or Path(command[0]).name
    _tui()._clear_terminal_for_external_command()
    print(f"Running setup {setup_id}: {command[0]}")
    try:
        result = _tui().subprocess.run(command, check=False)
    except KeyboardInterrupt:
        return 130
    return result.returncode

def _copy_logs(state):
    text = "\n".join(state.last_action_log or state.last_action_summary or ["No logs available."])
    try:
        _tui()._copy_text_to_clipboard(text)
    except Exception as exc:
        state.message = f"Copy failed: {exc}"
        return
    state.message = "Copied log text."

def _open_logs(state):
    if not state.last_action_log:
        state.last_action_log = ["No logs available."]
    _tui()._set_mode(state, "logs")

def _open_help(state):
    state.help_return_mode = state.mode if state.mode != "help" else (state.help_return_mode or "setup-manager")
    _tui()._set_mode(state, "help")
