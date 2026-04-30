"""Dashboard mode helpers: profile CRUD, step navigation, build resolution.

These functions don't reference any monkey-patched name directly. The action
layer in :mod:`cc_extractor.tui` re-exports them so internal callers and
tests resolve the names through the package globals.
"""

from typing import Optional

from ..download_index import download_versions, refresh_download_index
from ..downloader import download_binary
from ..workspace import (
    delete_patch_profile,
    native_artifact_from_path,
    rename_patch_profile,
    save_patch_profile,
    workspace_root,
)
from ._const import DASHBOARD_STEPS, SOURCE_ARTIFACT, SOURCE_LATEST, SOURCE_VERSION
from ._runtime import run_quiet
from .options import (
    dashboard_source_artifact,
    profile_by_id,
    profile_missing_refs,
    profile_refs_by_key,
    selected_dashboard_packages,
    selected_patch_refs,
)


def advance_dashboard(state):
    state.dashboard_step = min(state.dashboard_step + 1, len(DASHBOARD_STEPS) - 1)
    state.selected_index = 0


def reset_dashboard(state):
    state.dashboard_step = 0
    state.selected_index = 0
    state.selected_patch_indexes = []
    state.dashboard_source_kind = SOURCE_LATEST
    state.dashboard_source_version = ""
    state.dashboard_source_artifact_index = 0
    state.dashboard_profile_name = ""
    state.dashboard_loaded_profile_id = ""
    state.dashboard_delete_confirm_id = ""
    state.message = "Dashboard reset."


def toggle_dashboard_patch(state, index):
    if index in state.selected_patch_indexes:
        state.selected_patch_indexes.remove(index)
    else:
        state.selected_patch_indexes.append(index)
        state.selected_patch_indexes.sort()
    if state.dashboard_loaded_profile_id:
        state.dashboard_loaded_profile_id = ""


def require_dashboard_patches(state) -> bool:
    if not selected_dashboard_packages(state):
        state.message = "Select at least one patch package."
        return False
    return True


def refresh_dashboard_index(state):
    try:
        index, _output = run_quiet(refresh_download_index)
        state.download_index = index
        state.download_versions = download_versions(index, "binary")
        state.message = (
            f"Saved {len(state.download_versions)} native versions to "
            f"{workspace_root() / 'download-index.json'}"
        )
    except Exception as exc:
        state.message = f"Refresh failed: {exc}"


def load_dashboard_profile(state, profile_id: str) -> bool:
    profile = profile_by_id(state, profile_id)
    if profile is None:
        state.message = f"Profile not found: {profile_id}"
        return False

    missing = profile_missing_refs(state, profile)
    if missing:
        state.dashboard_loaded_profile_id = profile.profile_id
        state.message = f"Profile {profile.name} is invalid, missing {', '.join(missing)}"
        return False

    available = profile_refs_by_key(state)
    state.selected_patch_indexes = [
        available[(ref["id"], ref["version"])]
        for ref in profile.patches
    ]
    state.selected_patch_indexes.sort()
    state.dashboard_profile_name = profile.name
    state.dashboard_loaded_profile_id = profile.profile_id
    state.message = f"Loaded profile: {profile.name}"
    return True


def create_dashboard_profile(state):
    if not require_dashboard_patches(state):
        return
    try:
        profile = save_patch_profile(
            state.dashboard_profile_name,
            selected_patch_refs(state),
            overwrite=False,
        )
        state.dashboard_loaded_profile_id = profile.profile_id
        state.dashboard_profile_name = profile.name
        state.message = f"Created profile: {profile.name}"
    except Exception as exc:
        state.message = f"Create profile failed: {exc}"


def rename_dashboard_profile(state, profile_id: str):
    if not state.dashboard_profile_name.strip():
        state.message = "Type a non-empty profile name before renaming."
        return
    try:
        profile = rename_patch_profile(profile_id, state.dashboard_profile_name)
        if state.dashboard_loaded_profile_id == profile_id:
            state.dashboard_loaded_profile_id = profile.profile_id
        state.dashboard_profile_name = profile.name
        state.message = f"Renamed profile: {profile.name}"
    except Exception as exc:
        state.message = f"Rename profile failed: {exc}"


def overwrite_dashboard_profile(state, profile_id: str):
    if not require_dashboard_patches(state):
        return
    profile = profile_by_id(state, profile_id)
    if profile is None:
        state.message = f"Profile not found: {profile_id}"
        return
    try:
        updated = save_patch_profile(
            profile.name,
            selected_patch_refs(state),
            profile_id=profile.profile_id,
            overwrite=True,
        )
        state.dashboard_loaded_profile_id = updated.profile_id
        state.dashboard_profile_name = updated.name
        state.message = f"Overwrote profile: {updated.name}"
    except Exception as exc:
        state.message = f"Overwrite profile failed: {exc}"


def delete_dashboard_profile(state, profile_id: str):
    profile = profile_by_id(state, profile_id)
    if profile is None:
        state.message = f"Profile not found: {profile_id}"
        return
    if state.dashboard_delete_confirm_id != profile_id:
        state.dashboard_delete_confirm_id = profile_id
        state.message = f"Press Enter again to delete profile: {profile.name}"
        return
    try:
        delete_patch_profile(profile_id)
        if state.dashboard_loaded_profile_id == profile_id:
            state.dashboard_loaded_profile_id = ""
        state.dashboard_delete_confirm_id = ""
        state.message = f"Deleted profile: {profile.name}"
    except Exception as exc:
        state.message = f"Delete profile failed: {exc}"


def dashboard_artifact_for_run(state) -> Optional[object]:
    """Resolve the source artifact for a dashboard build (download if needed)."""
    if state.dashboard_source_kind == SOURCE_ARTIFACT:
        artifact = dashboard_source_artifact(state)
        if artifact is None:
            state.message = "Selected downloaded artifact is unavailable."
        return artifact

    requested_version = "latest"
    if state.dashboard_source_kind == SOURCE_VERSION:
        requested_version = state.dashboard_source_version
        if not requested_version:
            state.message = "Select a native version before running."
            return None

    path, _output = run_quiet(download_binary, requested_version)
    artifact = native_artifact_from_path(path)
    if artifact is None:
        state.message = f"Downloaded binary was not found in the workspace: {path}"
    return artifact


__all__ = [
    "advance_dashboard",
    "create_dashboard_profile",
    "dashboard_artifact_for_run",
    "delete_dashboard_profile",
    "load_dashboard_profile",
    "overwrite_dashboard_profile",
    "refresh_dashboard_index",
    "rename_dashboard_profile",
    "require_dashboard_patches",
    "reset_dashboard",
    "toggle_dashboard_patch",
]
