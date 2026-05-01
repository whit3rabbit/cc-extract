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
    elif state.mode == "tweaks-edit":
        if list(state.tweaks_pending) != list(state.tweaks_baseline):
            discard_tweaks(state)
        else:
            state.tweaks_variant_id = None
            state.tweaks_pending = []
            state.tweaks_baseline = ()
            set_mode(state, "tweaks-source")


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


def enter_tweaks_for_variant(state, variant_id: str) -> None:
    """Enter tweaks-edit mode scoped to the given variant."""
    variant = next((v for v in state.variants if v.variant_id == variant_id), None)
    if variant is None:
        state.message = f"Variant {variant_id!r} not found"
        return
    manifest = variant.manifest or {}
    baseline = tuple(manifest.get("tweaks", []) or [])
    state.tweaks_variant_id = variant_id
    state.tweaks_baseline = baseline
    state.tweaks_pending = list(baseline)
    state.message = ""
    set_mode(state, "tweaks-edit")


def toggle_tweak(state) -> None:
    """Toggle the patch under the cursor in `state.tweaks_pending`."""
    from .options import selected_tweaks_edit_option

    option = selected_tweaks_edit_option(state)
    if option is None or option.kind != "tweak-toggle":
        return
    patch_id = option.value
    if patch_id in state.tweaks_pending:
        state.tweaks_pending = [pid for pid in state.tweaks_pending if pid != patch_id]
    else:
        state.tweaks_pending = list(state.tweaks_pending) + [patch_id]
    _refresh_tweaks_pending_message(state)


def discard_tweaks(state) -> None:
    """Reset pending changes back to the baseline."""
    if state.tweaks_variant_id is None:
        return
    state.tweaks_pending = list(state.tweaks_baseline)
    state.message = "Discarded pending tweak changes."


def apply_tweaks(state) -> None:
    """Persist `tweaks_pending` to the variant manifest and rebuild."""
    if state.tweaks_variant_id is None:
        state.message = "No variant selected."
        return
    if list(state.tweaks_pending) == list(state.tweaks_baseline):
        state.message = "No tweak changes to apply."
        return

    # Local imports avoid circular imports + let tests monkey-patch them via
    # cc_extractor.tui.nav (or via cc_extractor.variants directly).
    from .. import variants as variants_module
    from ..variants.model import validate_variant_manifest
    from ..workspace import write_json

    variant_id = state.tweaks_variant_id
    pending = sorted(set(state.tweaks_pending))
    baseline_set = set(state.tweaks_baseline)
    pending_set = set(pending)
    added = sorted(pending_set - baseline_set)
    removed = sorted(baseline_set - pending_set)

    try:
        variant = variants_module.load_variant(variant_id)
    except Exception as exc:
        state.message = f"Failed to load variant: {exc}"
        return

    manifest = dict(variant.manifest or {})
    manifest["tweaks"] = pending

    try:
        validate_variant_manifest(manifest)
        write_json(variant.path / "variant.json", manifest)
    except Exception as exc:
        state.message = f"Failed to update manifest: {exc}"
        return

    claude_version = (manifest.get("source") or {}).get("version")
    try:
        run_quiet(variants_module.apply_variant, variant_id, claude_version=claude_version)
    except Exception as exc:
        state.message = f"Apply failed: {exc}"
        return

    # Refresh state from the now-rebuilt variant.
    state.refresh()
    refreshed = next((v for v in state.variants if v.variant_id == variant_id), None)
    if refreshed is not None:
        new_baseline = tuple((refreshed.manifest or {}).get("tweaks", []) or [])
        state.tweaks_baseline = new_baseline
        state.tweaks_pending = list(new_baseline)
    state.message = (
        f"Applied tweaks to {variant_id} "
        f"(+{len(added)} added, -{len(removed)} removed)."
    )


def _refresh_tweaks_pending_message(state) -> None:
    pending = set(state.tweaks_pending)
    baseline = set(state.tweaks_baseline)
    diff = (pending - baseline) | (baseline - pending)
    if not diff:
        state.message = ""
    else:
        state.message = (
            f"{len(diff)} pending change{'s' if len(diff) != 1 else ''} - "
            "press 'a' to apply, 'b' to discard"
        )
