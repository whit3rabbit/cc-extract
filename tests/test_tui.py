from pathlib import Path

from cc_extractor import tui
from cc_extractor.workspace import (
    DashboardTweakProfile,
    NativeArtifact,
    PatchPackage,
    PatchProfile,
    load_dashboard_tweak_profile,
    load_tui_settings,
    save_dashboard_tweak_profile,
    save_tui_settings,
)


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


def _tweak_profile(
    profile_id="daily-build",
    name="Daily Build",
    tweak_ids=None,
):
    tweak_ids = tweak_ids or [tui.DASHBOARD_TWEAK_IDS[0]]
    return DashboardTweakProfile(
        profile_id=profile_id,
        name=name,
        tweak_ids=tweak_ids,
        path=Path(f"/tmp/{profile_id}.json"),
        manifest={
            "schemaVersion": 1,
            "id": profile_id,
            "name": name,
            "tweakIds": tweak_ids,
        },
    )


def _render_screen(state, width=80, height=24):
    from ratatui_py import Color, DrawCmd, Gauge, List as TuiList, Paragraph, Style, Tabs, headless_render_frame

    class FakeTerm:
        def __init__(self):
            self.commands = None

        def draw_frame(self, commands):
            self.commands = commands

    term = FakeTerm()
    tui._render_frame(
        term, state, width, height,
        Paragraph, Style, Color, DrawCmd, Tabs, TuiList, Gauge,
    )
    return headless_render_frame(width, height, term.commands)


def test_screen_text_contains_dashboard_first_tab():
    state = tui.TuiState(
        counts="Native: 0  NPM: 0  Extractions: 0  Patch packages: 0  Profiles: 0",
        download_index={"binary": {"latest": "2.1.122"}},
        download_versions=["2.1.122", "2.1.121"],
    )

    screen = tui._screen_text(state)

    assert "Workspace:" in screen
    assert "cc-extractor | Manage Setup [Dashboard] Inspect Extract Patch" in screen
    assert "Dashboard Source | Step 1/4" in screen
    assert "Latest native binary" in screen
    assert "Native 2.1.121" in screen
    assert "Inspect" in screen
    assert "Extract" in screen
    assert "Patch" in screen


def test_default_theme_is_hacker_bbs():
    state = tui.TuiState()

    assert state.theme_id == "hacker-bbs"
    assert tui._theme_name(state.theme_id) == "Hacker BBS"
    assert tui._active_theme(state).theme_id == "hacker-bbs"


def test_cycle_theme_saves_workspace_setting(tmp_path, monkeypatch):
    root = tmp_path / ".cc-extractor"
    monkeypatch.setenv("CC_EXTRACTOR_WORKSPACE", str(root))
    state = tui.TuiState()

    seen = []
    for _ in range(4):
        tui._cycle_theme(state)
        seen.append(state.theme_id)

    assert seen == ["unicorn", "dark", "light", "hacker-bbs"]
    assert load_tui_settings(root)["themeId"] == "hacker-bbs"
    assert state.message == "Theme saved: Hacker BBS"


def test_load_saved_theme_id_uses_workspace_setting(tmp_path, monkeypatch):
    root = tmp_path / ".cc-extractor"
    save_tui_settings({"themeId": "dark"}, root=root)
    monkeypatch.setenv("CC_EXTRACTOR_WORKSPACE", str(root))

    assert tui._load_saved_theme_id() == "dark"


def test_load_saved_theme_id_falls_back_for_unknown_theme(tmp_path, monkeypatch):
    root = tmp_path / ".cc-extractor"
    save_tui_settings({"themeId": "unknown-theme"}, root=root)
    monkeypatch.setenv("CC_EXTRACTOR_WORKSPACE", str(root))

    assert tui._load_saved_theme_id() == "hacker-bbs"


def test_dashboard_theme_key_does_not_probe_variant_helpers(tmp_path, monkeypatch):
    root = tmp_path / ".cc-extractor"
    monkeypatch.setenv("CC_EXTRACTOR_WORKSPACE", str(root))

    def fail_variant_text_check(state):
        raise AssertionError("dashboard key handling should not check variant name text")

    monkeypatch.setattr(tui, "_variant_accepts_name_text", fail_variant_text_check)
    state = tui.TuiState(mode="dashboard")

    assert tui._handle_char_key(state, "t") is True
    assert state.theme_id == "unicorn"


def test_variant_name_text_accepts_lowercase_t(tmp_path, monkeypatch):
    root = tmp_path / ".cc-extractor"
    monkeypatch.setenv("CC_EXTRACTOR_WORKSPACE", str(root))
    state = tui.TuiState(mode="variants", variant_step=1, selected_index=0)

    assert tui._handle_char_key(state, "t") is True
    assert state.variant_name == "t"
    assert state.theme_id == "hacker-bbs"


def test_screen_text_includes_theme_and_compact_progress():
    state = tui.TuiState(
        counts="Native: 0  NPM: 0  Extractions: 0  Patch packages: 2  Profiles: 0",
        dashboard_step=1,
        selected_dashboard_tweak_ids=[tui.DASHBOARD_TWEAK_IDS[0]],
    )

    screen = tui._screen_text(state)

    assert "Theme: Hacker BBS" in screen
    assert "Dashboard Patches | Step 2/4" in screen
    assert "Patches 1" in screen
    assert "Wizard: [" not in screen
    assert "Theme T" in screen


def test_dashboard_first_run_lists_curated_tweaks_without_dead_end_continue():
    state = tui.TuiState(mode="dashboard", dashboard_step=1)

    screen = tui._screen_text(state)

    assert tui.DASHBOARD_TWEAK_IDS[0] in screen
    assert "Continue to profile management" not in screen

    tui._toggle_selected(state)
    assert state.selected_dashboard_tweak_ids == [tui.DASHBOARD_TWEAK_IDS[0]]

    screen = tui._screen_text(state)
    assert "Continue to profile management" in screen

    state.selected_dashboard_tweak_ids = []
    tui._activate_dashboard(state)
    assert state.selected_dashboard_tweak_ids == [tui.DASHBOARD_TWEAK_IDS[0]]


def test_footer_keys_match_dashboard_step():
    state = tui.TuiState(mode="dashboard", dashboard_step=0)
    footer = tui._footer_text(state)
    assert "Refresh R" in footer
    assert "Space toggle" not in footer

    state.dashboard_step = 1
    footer = tui._footer_text(state)
    assert "Space toggle" in footer
    assert "R refresh" not in footer

    state.dashboard_step = 2
    footer = tui._footer_text(state)
    assert "Profile names:" in footer


def test_footer_keys_match_variant_step():
    state = tui.TuiState(mode="variants", variant_step=1)
    footer = tui._footer_text(state)
    assert "Setup names:" in footer
    assert "Space toggle tweak" not in footer

    state.variant_step = 2
    footer = tui._footer_text(state)
    assert "Credential env:" in footer
    assert "Raw API keys are not accepted" in footer

    state.variant_step = 3
    footer = tui._footer_text(state)
    assert "Model aliases:" in footer

    state.variant_step = 4
    footer = tui._footer_text(state)
    assert "Space toggle tweak" in footer
    assert "Variant names:" not in footer


def test_activate_reports_action_and_refresh_failures(monkeypatch):
    state = tui.TuiState(mode="dashboard")

    def fail_action(app_state):
        raise RuntimeError("boom")

    def fail_refresh(app_state):
        raise RuntimeError("scan broke")

    monkeypatch.setattr(tui, "_activate_dashboard", fail_action)
    monkeypatch.setattr(tui.TuiState, "refresh", fail_refresh)

    assert tui._activate(state) is True
    assert "Action failed: boom" in state.message
    assert "Refresh failed: scan broke" in state.message


def test_gauge_widget_renders_with_headless_ratatui():
    from ratatui_py import Color, DrawCmd, Gauge, Style, headless_render_frame

    theme = tui._active_theme(tui.TuiState(theme_id="unicorn"))
    gauge = tui._gauge_widget("Wizard", 0.5, "2/4 Patches", Gauge, Style, Color, theme)
    screen = headless_render_frame(40, 3, [DrawCmd.gauge(gauge, (0, 0, 40, 3))])

    assert "Wizard" in screen
    assert "2/4 Patches" in screen


def test_render_frame_themes_full_surface():
    from ratatui_py import Color, DrawCmd, Gauge, List as TuiList, Paragraph, Style, Tabs, headless_render_frame_cells

    state = tui.TuiState(theme_id="light")

    class FakeTerm:
        def __init__(self):
            self.commands = None

        def draw_frame(self, commands):
            self.commands = commands

    term = FakeTerm()
    tui._render_frame(
        term, state, 80, 24,
        Paragraph, Style, Color, DrawCmd, Tabs, TuiList, Gauge,
    )

    cells = headless_render_frame_cells(80, 24, term.commands)

    assert cells
    assert all(cell["fg"] != int(Color.Reset) or cell["bg"] != int(Color.Reset) for cell in cells)


def test_render_frame_puts_theme_only_in_bottom_banner():
    state = tui.TuiState(theme_id="hacker-bbs")

    screen = _render_screen(state, 80, 24)
    lines = screen.splitlines()

    assert screen.count("Theme: Hacker BBS") == 1
    assert all("Theme:" not in line for line in lines[:4])
    assert "Theme: Hacker BBS" in "\n".join(lines[-5:])


def test_render_frame_uses_stable_chrome_for_dashboard_and_inspect():
    dashboard = tui.TuiState(mode="dashboard")
    inspect = tui.TuiState(mode="inspect")

    assert tui.rendering.layout_heights(24) == (4, 5)

    dashboard_lines = _render_screen(dashboard, 80, 24).splitlines()
    inspect_lines = _render_screen(inspect, 80, 24).splitlines()

    assert "Dashboard: Source" in dashboard_lines[4]
    assert "Inspect" in inspect_lines[4]
    assert "Status" in dashboard_lines[-5]
    assert "Status" in inspect_lines[-5]


def test_render_frame_keeps_body_and_footer_at_short_height():
    state = tui.TuiState(
        download_index={"binary": {"latest": "2.1.122"}},
        download_versions=["2.1.122", "2.1.121"],
    )

    screen = _render_screen(state, 80, 18)

    assert "Latest native binary" in screen
    assert "Status: Ready" in screen
    assert "Theme: Hacker BBS" in screen


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
    first = tui.DASHBOARD_TWEAK_IDS[0]
    second = tui.DASHBOARD_TWEAK_IDS[1]
    state = tui.TuiState(
        mode="dashboard",
        dashboard_step=1,
        dashboard_tweak_profiles=[_tweak_profile(tweak_ids=[first, second])],
    )

    state.selected_index = 0
    tui._activate_dashboard(state)
    assert state.selected_dashboard_tweak_ids == [first]

    state.selected_index = next(
        index for index, option in enumerate(tui._dashboard_options(state))
        if option.kind == "profile-load"
    )
    tui._activate_dashboard(state)
    assert state.selected_dashboard_tweak_ids == [first, second]
    assert state.dashboard_loaded_profile_id == "daily-build"
    assert state.dashboard_profile_name == "Daily Build"


def test_dashboard_marks_profile_with_missing_patch_invalid():
    first = tui.DASHBOARD_TWEAK_IDS[0]
    state = tui.TuiState(
        mode="dashboard",
        dashboard_step=1,
        dashboard_tweak_profiles=[_tweak_profile(tweak_ids=[first, "missing-patch"])],
    )

    screen = tui._screen_text(state)
    state.selected_index = next(
        index for index, option in enumerate(tui._dashboard_options(state))
        if option.kind == "profile-load"
    )
    tui._activate_dashboard(state)

    assert "invalid, missing missing-patch" in screen
    assert state.selected_dashboard_tweak_ids == []
    assert "missing missing-patch" in state.message


def test_dashboard_run_rejects_legacy_patch_profile_id():
    state = tui.TuiState(
        mode="dashboard",
        dashboard_step=3,
        dashboard_loaded_profile_id="legacy-package-profile",
        patch_profiles=[_profile(profile_id="legacy-package-profile", name="Legacy Package Profile")],
        selected_dashboard_tweak_ids=[tui.DASHBOARD_TWEAK_IDS[0]],
    )

    tui._run_dashboard_build(state)

    assert state.message == (
        "Loaded profile is invalid, missing legacy-package-profile is not a dashboard tweak profile"
    )


def test_dashboard_creates_profile_from_selected_patches(tmp_path, monkeypatch):
    first = tui.DASHBOARD_TWEAK_IDS[0]
    monkeypatch.setenv("CC_EXTRACTOR_WORKSPACE", str(tmp_path / ".cc-extractor"))
    state = tui.TuiState(
        mode="dashboard",
        dashboard_step=2,
        selected_dashboard_tweak_ids=[first],
        dashboard_profile_name="Focus Build",
    )

    tui._create_dashboard_profile(state)

    profile = load_dashboard_tweak_profile("focus-build", root=tmp_path / ".cc-extractor")
    assert profile.name == "Focus Build"
    assert profile.tweak_ids == [first]
    assert state.dashboard_loaded_profile_id == "focus-build"


def test_dashboard_delete_profile_requires_confirmation(tmp_path, monkeypatch):
    root = tmp_path / ".cc-extractor"
    monkeypatch.setenv("CC_EXTRACTOR_WORKSPACE", str(root))
    state = tui.TuiState(
        mode="dashboard",
        dashboard_step=2,
        dashboard_tweak_profiles=[_tweak_profile()],
        dashboard_loaded_profile_id="daily-build",
    )

    save_dashboard_tweak_profile("Daily Build", [tui.DASHBOARD_TWEAK_IDS[0]], root=root)

    tui._delete_dashboard_profile(state, "daily-build")
    assert state.dashboard_delete_confirm_id == "daily-build"
    assert load_dashboard_tweak_profile("daily-build", root=root).name == "Daily Build"

    tui._delete_dashboard_profile(state, "daily-build")
    assert state.dashboard_delete_confirm_id == ""
    assert state.dashboard_loaded_profile_id == ""


def test_dashboard_run_requires_patches():
    state = tui.TuiState(mode="dashboard", dashboard_step=3)

    tui._run_dashboard_build(state)

    assert state.message == "Select at least one dashboard patch."


def test_dashboard_run_applies_selected_tweaks_to_artifact(monkeypatch, tmp_path):
    calls = []
    artifact = NativeArtifact(
        version="2.1.123",
        platform="darwin-arm64",
        sha256="a" * 64,
        path=tmp_path / "claude",
        metadata={},
    )

    class Result:
        output_path = tmp_path / "claude-patched"

    def fake_apply(source_artifact, tweak_ids):
        calls.append((source_artifact, tweak_ids))
        return Result()

    monkeypatch.setattr(tui, "apply_dashboard_tweaks_to_native", fake_apply)

    state = tui.TuiState(
        mode="dashboard",
        dashboard_step=3,
        dashboard_source_kind=tui.SOURCE_ARTIFACT,
        native_artifacts=[artifact],
        selected_dashboard_tweak_ids=[tui.DASHBOARD_TWEAK_IDS[0]],
    )

    tui._run_dashboard_build(state)

    assert calls == [(artifact, [tui.DASHBOARD_TWEAK_IDS[0]])]
    assert state.message == f"Dashboard build complete: {tmp_path / 'claude-patched'}"


def test_patch_package_apply_handles_stale_selection(monkeypatch, tmp_path):
    artifact = NativeArtifact(
        version="1.2.3",
        platform="darwin-arm64",
        sha256="a" * 64,
        path=tmp_path / "claude",
        metadata={},
    )
    calls = []

    def fake_apply(source_artifact, packages):
        calls.append((source_artifact, packages))

    monkeypatch.setattr(tui, "apply_patch_packages_to_native", fake_apply)
    state = tui.TuiState(
        mode="patch-package",
        native_artifacts=[artifact],
        selected_source_index=0,
        patch_packages=[],
        selected_patch_indexes=[3],
    )

    tui._activate_patch_packages(state)

    assert calls == []
    assert state.message == "Selected patch packages are unavailable."


def test_move_tab_cycles_from_dashboard_to_inspect():
    state = tui.TuiState(mode="dashboard")

    tui._move_tab(state, 1)

    assert state.mode == "inspect"


def test_move_tab_clears_stale_status():
    state = tui.TuiState(mode="dashboard", message="Select at least one patch package.")

    tui._move_tab(state, 1)

    assert state.mode == "inspect"
    assert state.message == ""


def test_variants_tab_lists_providers_and_progress():
    state = tui.TuiState(
        mode="variants",
        variant_providers=[
            {
                "key": "mirror",
                "label": "Mirror Claude",
                "description": "Pure Claude",
                "defaultVariantName": "mirror",
            }
        ],
    )

    screen = tui._screen_text(state)

    assert "[Manage Setup]" in screen
    assert "Create setup Provider | Step 1/6" in screen
    assert "mirror  Mirror Claude" in screen


def test_variants_wizard_selects_provider_toggles_tweak_and_creates(monkeypatch, tmp_path):
    calls = []

    class Result:
        wrapper_path = tmp_path / ".cc-extractor" / "bin" / "mirror"

    def fake_create_variant(**kwargs):
        calls.append(kwargs)
        return Result()

    monkeypatch.setattr(tui, "create_variant", fake_create_variant)
    state = tui.TuiState(
        mode="variants",
        variant_providers=[
            {
                "key": "mirror",
                "label": "Mirror Claude",
                "description": "Pure Claude",
                "authMode": "none",
                "credentialEnv": "",
                "models": {},
                "defaultVariantName": "mirror",
            }
        ],
    )

    state.selected_index = 0
    tui._activate_variants(state)
    assert state.variant_step == 1
    assert state.variant_name == "mirror"

    state.selected_index = 1
    tui._activate_variants(state)
    assert state.variant_step == 2

    state.selected_index = 1
    tui._activate_variants(state)
    assert state.variant_step == 4

    state.selected_index = 0
    first_tweak = state.selected_variant_tweaks[0]
    tui._toggle_selected(state)
    assert first_tweak not in state.selected_variant_tweaks

    state.selected_index = len(tui.DEFAULT_TWEAK_IDS) + 1
    tui._activate_variants(state)
    assert state.variant_step == 5

    tui._activate_variants(state)
    assert calls[0]["provider_key"] == "mirror"
    assert calls[0]["name"] == "mirror"
    assert calls[0]["credential_env"] is None
    assert calls[0]["model_overrides"] == {}
    assert first_tweak not in calls[0]["tweaks"]


def test_variants_wizard_blocks_required_model_mapping():
    state = tui.TuiState(
        mode="variants",
        variant_step=3,
        selected_index=len(tui.VARIANT_MODEL_FIELDS),
        variant_provider_index=0,
        variant_providers=[
            {
                "key": "openrouter",
                "label": "OpenRouter",
                "description": "Gateway",
                "authMode": "authToken",
                "credentialEnv": "OPENROUTER_API_KEY",
                "requiresModelMapping": True,
                "models": {},
                "defaultVariantName": "openrouter",
            }
        ],
    )

    tui._activate_variants(state)

    assert state.variant_step == 3
    assert state.message == "Set model aliases for: Opus, Sonnet, Haiku"

    state.variant_model_overrides = {
        "opus": "anthropic/claude-opus-4",
        "sonnet": "anthropic/claude-sonnet-4",
        "haiku": "anthropic/claude-haiku-4",
    }
    tui._activate_variants(state)

    assert state.variant_step == 4


def test_variants_text_inputs_cover_credentials_and_models():
    state = tui.TuiState(mode="variants", variant_step=2, selected_index=0, variant_credential_env="Z_AI_API_KE")

    assert tui._handle_char_key(state, "Y") is True
    assert state.variant_credential_env == "Z_AI_API_KEY"
    assert tui._variant_backspace(state) is True
    assert state.variant_credential_env == "Z_AI_API_KE"

    state.variant_step = 3
    state.selected_index = 0
    assert tui._handle_char_key(state, "g") is True
    assert tui._handle_char_key(state, "l") is True
    assert state.variant_model_overrides["opus"] == "gl"


def test_setup_manager_health_reports_doctor_failure(monkeypatch):
    class Variant:
        variant_id = "mirror"
        name = "Mirror"
        path = Path("/tmp/mirror")
        manifest = {
            "provider": {"key": "mirror"},
            "source": {"version": "2.1.123"},
            "paths": {"wrapper": "/tmp/mirror"},
            "tweaks": [],
        }

    def fail_doctor(name):
        raise RuntimeError("doctor broke")

    monkeypatch.setattr(tui, "doctor_variant", fail_doctor)
    state = tui.TuiState(mode="setup-manager", variants=[Variant()], selected_index=1)

    tui._handle_char_key(state, "h")

    assert state.message == "Health for setup mirror: broken"
    assert state.setup_health["mirror"]["status"] == "broken"


# -- Tweaks tab tests ----------------------------------------------------------

def _variant(variant_id="my-variant", name="My Variant", tweaks=None, version="2.1.123"):
    from cc_extractor.variants.model import Variant
    tweaks = list(tweaks or [])
    return Variant(
        variant_id=variant_id,
        name=name,
        path=Path(f"/tmp/{variant_id}"),
        manifest={
            "schemaVersion": 1,
            "id": variant_id,
            "name": name,
            "provider": {"key": "kimi", "label": "Kimi"},
            "source": {"version": version, "platform": "darwin-arm64", "sha256": "x", "path": "/tmp/x"},
            "paths": {"wrapper": f"/tmp/bin/{variant_id}"},
            "tweaks": tweaks,
            "runtime": "native",
        },
    )


def test_startup_routes_to_first_run_or_setup_manager():
    empty = tui.TuiState(mode="loading")
    tui._route_startup(empty)
    assert empty.mode == "first-run-setup"
    assert "No Claude Code setups found" in empty.message

    variant = _variant("deepseek-main")
    existing = tui.TuiState(mode="loading", variants=[variant])
    tui._route_startup(existing)
    assert existing.mode == "setup-manager"
    assert existing.selected_setup_id == "deepseek-main"


def test_setup_manager_lists_rows_and_opens_detail():
    variant = _variant("deepseek-main")
    state = tui.TuiState(
        mode="setup-manager",
        variants=[variant],
        setup_health={"deepseek-main": {"status": "healthy"}},
        selected_index=1,
    )

    screen = tui._screen_text(state)
    assert "Setup manager" in screen
    assert "Name" in screen
    assert "Provider" in screen
    assert "Health" in screen
    assert "deepseek-main" in screen
    assert "healthy" in screen
    assert "deepseek-main" in screen

    tui._activate_setup_manager(state)
    assert state.mode == "setup-detail"
    assert state.selected_setup_id == "deepseek-main"


def test_upgrade_preview_applies_update_and_health(monkeypatch, tmp_path):
    variant = _variant("deepseek-main", version="2.1.122")
    calls = []

    class Result:
        wrapper_path = tmp_path / "cc-deepseek"

    def fake_update(name, *, claude_version=None):
        calls.append((name, claude_version))
        return [Result()]

    def fake_refresh(state_arg):
        variant.manifest["source"]["version"] = "2.1.123"
        state_arg.variants = [variant]
        return True

    def fake_doctor(name):
        return [{"id": name, "ok": True, "checks": [{"name": "wrapper", "ok": True, "path": "/tmp/bin/deepseek-main"}]}]

    monkeypatch.setattr(tui, "update_variants", fake_update)
    monkeypatch.setattr(tui, "_refresh_state", fake_refresh)
    monkeypatch.setattr(tui, "doctor_variant", fake_doctor)
    state = tui.TuiState(mode="upgrade-preview", variants=[variant], selected_setup_id="deepseek-main")

    tui._run_setup_upgrade(state)

    assert calls == [("deepseek-main", "latest")]
    assert state.mode == "health-result"
    assert "2.1.122 -> 2.1.123" in "\n".join(state.last_action_summary)
    assert "Health: healthy" in "\n".join(state.last_action_summary)


def test_delete_requires_typed_setup_id(monkeypatch, tmp_path):
    variant = _variant("deepseek-main")
    variant.path = tmp_path / "deepseek-main"
    variant.path.mkdir()
    wrapper = tmp_path / "cc-deepseek"
    wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
    variant.manifest["paths"]["wrapper"] = str(wrapper)
    calls = []

    def fake_remove(name, *, yes=False):
        calls.append((name, yes))
        wrapper.unlink()
        variant.path.rmdir()
        return True

    def fake_refresh(state_arg):
        state_arg.variants = []
        return True

    monkeypatch.setattr(tui, "remove_variant", fake_remove)
    monkeypatch.setattr(tui, "_refresh_state", fake_refresh)
    state = tui.TuiState(
        mode="delete-confirm",
        variants=[variant],
        selected_setup_id="deepseek-main",
        delete_confirm_text="wrong",
    )

    tui._run_setup_delete(state)
    assert calls == []
    assert "exactly" in state.message

    state.delete_confirm_text = "deepseek-main"
    tui._run_setup_delete(state)
    assert calls == [("deepseek-main", True)]
    assert state.mode == "setup-manager"
    assert "Shared downloads untouched: yes" in "\n".join(state.last_action_summary)


def test_tweak_apply_uses_preview_then_post_health(monkeypatch):
    variant = _variant("deepseek-main", tweaks=["themes"])
    state = tui.TuiState(
        mode="tweak-editor",
        variants=[variant],
        selected_setup_id="deepseek-main",
        tweaks_variant_id="deepseek-main",
        tweaks_baseline=("themes",),
        tweaks_pending=["themes", "patches-applied-indication"],
    )

    tui._begin_tweak_apply_preview(state)
    assert state.tweak_apply_preview is True
    assert "Tweak rebuild preview" in tui._screen_text(state)

    def fake_apply(app_state):
        app_state.tweaks_baseline = tuple(app_state.tweaks_pending)
        app_state.message = "Applied tweaks to setup deepseek-main (+1 added, -0 removed)."

    def fake_doctor(name):
        return [{"id": name, "ok": True, "checks": []}]

    monkeypatch.setattr(tui, "_apply_tweaks", fake_apply)
    monkeypatch.setattr(tui, "doctor_variant", fake_doctor)

    tui._run_tweak_apply(state)

    assert state.mode == "health-result"
    assert state.last_tweak_result == {
        "added": ["patches-applied-indication"],
        "removed": [],
        "health": "healthy",
    }


def test_tweaks_tab_initial_state():
    state = tui.TuiState(mode="tweaks-source", variants=[_variant()])
    title, labels = tui.rendering.current_labels(state)
    assert title.startswith("Tweaks: pick setup")
    assert any("my-variant" in label for label in labels)


def test_tweaks_select_variant_enters_edit_mode():
    variant = _variant(tweaks=["themes", "hide-startup-banner"])
    state = tui.TuiState(mode="tweaks-source", variants=[variant])

    tui._activate(state)

    assert state.mode == "tweak-editor"
    assert state.tweaks_variant_id == variant.variant_id
    assert state.tweaks_baseline == ("themes", "hide-startup-banner")
    assert state.tweaks_pending == ["themes", "hide-startup-banner"]


def test_tweaks_toggle_updates_pending():
    variant = _variant(tweaks=["themes"])
    state = tui.TuiState(mode="tweaks-source", variants=[variant])
    tui._activate(state)  # enter edit mode
    state.selected_index = 0

    tui._toggle_tweak(state)

    assert "patches-applied-indication" in state.tweaks_pending
    assert "1 pending change" in state.message


def test_tweaks_discard_reverts():
    variant = _variant(tweaks=["themes"])
    state = tui.TuiState(mode="tweaks-source", variants=[variant])
    tui._activate(state)
    state.selected_index = 0
    tui._toggle_tweak(state)
    assert state.tweaks_pending != list(state.tweaks_baseline)

    tui._discard_tweaks(state)

    assert state.tweaks_pending == list(state.tweaks_baseline)
    assert "Discarded" in state.message


def test_tweaks_apply_calls_apply_variant(monkeypatch, tmp_path):
    variant = _variant(tweaks=["themes"])
    variant.path = tmp_path / variant.variant_id
    variant.path.mkdir()
    state = tui.TuiState(mode="tweaks-source", variants=[variant])
    tui._activate(state)
    state.selected_index = 0
    tui._toggle_tweak(state)
    pending_before_apply = list(state.tweaks_pending)

    written = {}

    class FakeBuildResult:
        wrapper_path = tmp_path / "wrapper"

    def fake_apply_variant(variant_id, *, claude_version=None, root=None):
        written["called_with"] = (variant_id, claude_version)
        return FakeBuildResult()

    def fake_load_variant(variant_id, root=None):
        return variant

    def fake_validate(manifest):
        written["validated"] = manifest

    def fake_write_json(path, manifest):
        written["written_path"] = path
        written["manifest"] = manifest

    # Refresh after apply re-scans variants; return the same variant with updated tweaks.
    def fake_refresh(state_arg):
        # Simulate the rebuild updating the variant on disk; pending becomes baseline.
        new_tweaks = sorted(set(pending_before_apply))
        variant.manifest["tweaks"] = new_tweaks
        state_arg.variants = [variant]
        return True

    monkeypatch.setattr("cc_extractor.variants.apply_variant", fake_apply_variant)
    monkeypatch.setattr("cc_extractor.variants.load_variant", fake_load_variant)
    monkeypatch.setattr("cc_extractor.variants.model.validate_variant_manifest", fake_validate)
    monkeypatch.setattr("cc_extractor.workspace.write_json", fake_write_json)
    monkeypatch.setattr(tui, "_refresh_state", fake_refresh)

    tui._apply_tweaks(state)

    assert written["called_with"] == (variant.variant_id, "2.1.123")
    assert written["manifest"]["tweaks"] == sorted(set(pending_before_apply))
    assert "Applied tweaks" in state.message


def test_tweaks_screen_text_two_pane():
    variant = _variant(tweaks=["themes"])
    state = tui.TuiState(mode="tweaks-source", variants=[variant])
    tui._activate(state)  # enter edit

    text = tui._screen_text(state, height=40)

    assert "Edit tweaks" in text
    assert "Tweak details" in text
    assert "Group:" in text
    assert "Versions supported" in text


def test_tweaks_two_pane_renders_at_typical_widths():
    from ratatui_py import Color, DrawCmd, Gauge, List as TuiList, Paragraph, Style, Tabs, headless_render_frame

    variant = _variant(tweaks=["themes"])
    state = tui.TuiState(mode="tweaks-source", variants=[variant], theme_id="hacker-bbs")
    tui._activate(state)  # enter tweaks-edit

    class FakeTerm:
        def __init__(self, w, h):
            self._w, self._h = w, h
            self.commands = None
        def size(self):
            return self._w, self._h
        def draw_frame(self, commands):
            self.commands = commands

    for width, height in ((100, 30), (80, 24)):
        term = FakeTerm(width, height)
        tui._render_frame(
            term, state, width, height,
            Paragraph, Style, Color, DrawCmd, Tabs, TuiList, Gauge,
        )
        assert term.commands, f"no commands at {width}x{height}"

        screen = headless_render_frame(width, height, term.commands)
        assert "Edit tweaks" in screen
        assert "Tweak details" in screen
        # ensure the right pane content was actually rendered
        assert "Group:" in screen
