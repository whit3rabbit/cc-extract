from pathlib import Path

from cc_extractor import tui
from cc_extractor.workspace import NativeArtifact, PatchPackage, PatchProfile, load_patch_profile


def _package(patch_id="replace-before", version="0.1.0", name="Replace Before"):
    return PatchPackage(
        patch_id=patch_id,
        version=version,
        name=name,
        path=Path(f"/tmp/{patch_id}/{version}"),
        manifest={"id": patch_id, "version": version, "name": name},
    )


def _profile(
    profile_id="daily-build",
    name="Daily Build",
    patches=None,
):
    patches = patches or [{"id": "replace-before", "version": "0.1.0"}]
    return PatchProfile(
        profile_id=profile_id,
        name=name,
        patches=patches,
        path=Path(f"/tmp/{profile_id}.json"),
        manifest={
            "schemaVersion": 1,
            "id": profile_id,
            "name": name,
            "patches": patches,
        },
    )


def test_screen_text_contains_dashboard_first_tab():
    state = tui.TuiState(
        counts="Native: 0  NPM: 0  Extractions: 0  Patch packages: 0  Profiles: 0",
        download_index={"binary": {"latest": "2.1.122"}},
        download_versions=["2.1.122", "2.1.121"],
    )

    screen = tui._screen_text(state)

    assert "Workspace:" in screen
    assert "Tabs: [Dashboard]" in screen
    assert "Steps: [Source] > Patches > Profiles > Review" in screen
    assert "Latest native binary" in screen
    assert "Native 2.1.121" in screen
    assert "Inspect" in screen
    assert "Extract" in screen
    assert "Patch" in screen


def test_dashboard_selects_specific_version_without_downloading():
    state = tui.TuiState(
        mode="dashboard",
        dashboard_step=0,
        selected_index=3,
        download_index={"binary": {"latest": "2.1.122"}},
        download_versions=["2.1.122", "2.1.121"],
    )

    tui._activate_dashboard(state)

    assert state.dashboard_step == 1
    assert state.dashboard_source_kind == tui.SOURCE_VERSION
    assert state.dashboard_source_version == "2.1.121"


def test_dashboard_toggles_patch_and_loads_profile():
    state = tui.TuiState(
        mode="dashboard",
        dashboard_step=1,
        patch_packages=[_package(), _package("second-patch", "0.2.0", "Second Patch")],
        patch_profiles=[
            _profile(
                patches=[
                    {"id": "replace-before", "version": "0.1.0"},
                    {"id": "second-patch", "version": "0.2.0"},
                ]
            )
        ],
    )

    state.selected_index = 0
    tui._activate_dashboard(state)
    assert state.selected_patch_indexes == [0]

    state.selected_index = 3
    tui._activate_dashboard(state)
    assert state.selected_patch_indexes == [0, 1]
    assert state.dashboard_loaded_profile_id == "daily-build"
    assert state.dashboard_profile_name == "Daily Build"


def test_dashboard_marks_profile_with_missing_patch_invalid():
    state = tui.TuiState(
        mode="dashboard",
        dashboard_step=1,
        patch_packages=[_package()],
        patch_profiles=[
            _profile(
                patches=[
                    {"id": "replace-before", "version": "0.1.0"},
                    {"id": "missing-patch", "version": "9.9.9"},
                ]
            )
        ],
    )

    screen = tui._screen_text(state)
    state.selected_index = 2
    tui._activate_dashboard(state)

    assert "invalid, missing missing-patch@9.9.9" in screen
    assert state.selected_patch_indexes == []
    assert "missing missing-patch@9.9.9" in state.message


def test_dashboard_creates_profile_from_selected_patches(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_EXTRACTOR_WORKSPACE", str(tmp_path / ".cc-extractor"))
    state = tui.TuiState(
        mode="dashboard",
        dashboard_step=2,
        patch_packages=[_package()],
        selected_patch_indexes=[0],
        dashboard_profile_name="Focus Build",
    )

    tui._create_dashboard_profile(state)

    profile = load_patch_profile("focus-build", root=tmp_path / ".cc-extractor")
    assert profile.name == "Focus Build"
    assert profile.patches == [{"id": "replace-before", "version": "0.1.0"}]
    assert state.dashboard_loaded_profile_id == "focus-build"


def test_dashboard_delete_profile_requires_confirmation(tmp_path, monkeypatch):
    root = tmp_path / ".cc-extractor"
    monkeypatch.setenv("CC_EXTRACTOR_WORKSPACE", str(root))
    state = tui.TuiState(
        mode="dashboard",
        dashboard_step=2,
        patch_profiles=[_profile()],
        dashboard_loaded_profile_id="daily-build",
    )

    from cc_extractor.workspace import save_patch_profile

    save_patch_profile("Daily Build", [{"id": "replace-before", "version": "0.1.0"}], root=root)

    tui._delete_dashboard_profile(state, "daily-build")
    assert state.dashboard_delete_confirm_id == "daily-build"
    assert load_patch_profile("daily-build", root=root).name == "Daily Build"

    tui._delete_dashboard_profile(state, "daily-build")
    assert state.dashboard_delete_confirm_id == ""
    assert state.dashboard_loaded_profile_id == ""


def test_dashboard_run_requires_patches():
    state = tui.TuiState(mode="dashboard", dashboard_step=3)

    tui._run_dashboard_build(state)

    assert state.message == "Select at least one patch package."


def test_dashboard_run_applies_selected_packages_to_artifact(monkeypatch, tmp_path):
    calls = []
    artifact = NativeArtifact(
        version="1.2.3",
        platform="darwin-arm64",
        sha256="a" * 64,
        path=tmp_path / "claude",
        metadata={},
    )

    class Result:
        output_path = tmp_path / "claude-patched"

    def fake_apply(source_artifact, packages):
        calls.append((source_artifact, packages))
        return Result()

    monkeypatch.setattr(tui, "apply_patch_packages_to_native", fake_apply)

    state = tui.TuiState(
        mode="dashboard",
        dashboard_step=3,
        dashboard_source_kind=tui.SOURCE_ARTIFACT,
        native_artifacts=[artifact],
        patch_packages=[_package()],
        selected_patch_indexes=[0],
    )

    tui._run_dashboard_build(state)

    assert calls == [(artifact, [state.patch_packages[0]])]
    assert state.message == f"Dashboard build complete: {tmp_path / 'claude-patched'}"


def test_move_tab_cycles_from_dashboard_to_inspect():
    state = tui.TuiState(mode="dashboard")

    tui._move_tab(state, 1)

    assert state.mode == "inspect"
