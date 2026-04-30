"""Tab/mode navigation, simple toggles, and inspect/extract activators.

None of these helpers reference monkey-patched names. The action-layer in
:mod:`cc_extractor.tui` re-exports them for tests that reach in via
``tui._move_tab`` / ``tui._activate_extract``.
"""

from ..bun_extract import parse_bun_binary
from ..extractor import extract_all
from ..workspace import (
    extraction_paths,
    short_sha,
    workspace_root,
)
from ._const import TABS, TAB_MODES
from ._runtime import run_quiet
from .rendering import active_tab


def set_mode(state, mode: str) -> None:
    state.mode = mode
    state.selected_index = 0


def move_tab(state, offset: int) -> None:
    active = active_tab(state)
    current = TABS.index(active)
    next_index = (current + offset) % len(TABS)
    set_mode(state, TAB_MODES[next_index])


def go_back(state) -> None:
    if state.mode == "dashboard":
        if state.dashboard_delete_confirm_id:
            state.dashboard_delete_confirm_id = ""
            state.message = "Delete cancelled."
            return
        if state.dashboard_step > 0:
            state.dashboard_step -= 1
            state.selected_index = 0
    elif state.mode == "patch-package":
        set_mode(state, "patch-source")
    elif state.mode == "variants":
        if state.variant_step > 0:
            state.variant_step -= 1
            state.selected_index = 0


def toggle_patch(state) -> None:
    if not state.patch_packages:
        return
    index = state.selected_index
    if index in state.selected_patch_indexes:
        state.selected_patch_indexes.remove(index)
    else:
        state.selected_patch_indexes.append(index)
        state.selected_patch_indexes.sort()


def selected_artifact(state):
    if not state.native_artifacts:
        state.message = "No centralized native downloads found."
        return None
    return state.native_artifacts[state.selected_index]


def source_artifact(state):
    if not state.native_artifacts:
        return None
    index = max(0, min(state.selected_source_index, len(state.native_artifacts) - 1))
    return state.native_artifacts[index]


def activate_inspect(state):
    artifact = selected_artifact(state)
    if artifact is None:
        return
    try:
        data = artifact.path.read_bytes()
        info = parse_bun_binary(data)
        entry = info.modules[info.entry_point_id].name if 0 <= info.entry_point_id < len(info.modules) else "unknown"
        state.message = (
            f"{artifact.version} {artifact.platform} {short_sha(artifact.sha256)}: "
            f"{info.platform}, {len(info.modules)} modules, entry {entry}"
        )
    except Exception as exc:
        state.message = f"Inspect failed: {exc}"


def activate_extract(state):
    artifact = selected_artifact(state)
    if artifact is None:
        return
    try:
        run_quiet(extract_all, str(artifact.path), source_version=artifact.version)
        _, bundle_path = extraction_paths(artifact.version, artifact.platform, artifact.sha256)
        state.message = f"Extraction ready: {bundle_path}"
    except Exception as exc:
        state.message = f"Extract failed: {exc}"


def activate_patch_source(state):
    artifact = selected_artifact(state)
    if artifact is None:
        return
    if not state.patch_packages:
        state.message = f"No patch packages found under {workspace_root() / 'patches' / 'packages'}"
        return
    state.selected_source_index = state.selected_index
    state.selected_patch_indexes = []
    set_mode(state, "patch-package")
