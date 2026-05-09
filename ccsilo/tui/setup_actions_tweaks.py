"""Dashboard build and tweak-apply actions for the TUI."""

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
from .setup_actions_setup import _run_setup_health

__all__ = [
    "_begin_tweak_apply_preview",
    "_run_tweak_apply",
    "_run_dashboard_build",
]

def _begin_tweak_apply_preview(state):
    if list(state.tweaks_pending) == list(state.tweaks_baseline):
        state.message = "No tweak changes to apply."
        return
    unsupported = _tui()._unsupported_pending_tweaks(state)
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
    added, removed = _tui()._tweak_diff(state)
    state.tweak_apply_preview = False
    _tui()._apply_tweaks(state)
    rebuild_log = list(state.last_action_log)
    if not state.message.startswith("Applied tweaks"):
        state.last_action_summary = _append_backend_stages([state.message], _stage_lines_from_log(rebuild_log))
        message = state.message
        _tui()._set_mode(state, "health-result")
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
    _tui()._set_mode(state, "health-result")
    state.message = message

def _run_dashboard_build(state):
    if not _tui()._require_dashboard_patches(state):
        return

    loaded_profile = _tui()._loaded_profile(state)
    if loaded_profile is not None:
        missing = _tui()._dashboard_tweak_profile_missing_ids(state, loaded_profile)
        if missing:
            state.message = f"Loaded profile is invalid, missing {', '.join(missing)}"
            return

    tweak_ids = _tui()._selected_dashboard_tweaks(state)
    try:
        artifact = _tui()._dashboard_artifact_for_run(state)
        if artifact is None:
            return
        result, _output = _run_quiet(apply_dashboard_tweaks_to_native, artifact, tweak_ids)
        state.message = f"Dashboard build complete: {result.output_path}"
    except Exception as exc:
        state.message = f"Dashboard build failed: {exc}"
