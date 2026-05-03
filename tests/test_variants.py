import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cc_extractor.bun_extract import parse_bun_binary
from cc_extractor.variants import (
    VariantBuildError,
    apply_variant,
    create_variant,
    doctor_variant,
    load_variant,
    remove_variant,
    run_variant,
    scan_variants,
)
from cc_extractor.variants.builder import patch_entry_js
from cc_extractor.variants.wrapper import write_wrapper
import cc_extractor.variants.wrapper as wrapper_module
from cc_extractor.variants.wrapper import write_secrets
from cc_extractor.workspace import NativeArtifact
from tests.helpers.bun_fixture import build_bun_fixture


ENTRY_JS = "\n".join(
    [
        'function getNames(){return{"dark":"Dark mode","light":"Light mode"}}',
        'const themeOptions=[{label:"Dark mode",value:"dark"},{label:"Light mode",value:"light"}];',
        'function pickTheme(A){switch(A){case"light":return LX9;case"dark":return CX9;default:return CX9}}',
        'let WEBFETCH=`Fetches URLs.\\n- For GitHub URLs, prefer using the gh CLI via Bash instead (e.g., gh pr view, gh issue view, gh api).`;',
        'const version=`${pkg.VERSION} (Claude Code)`;',
        ',R.createElement(B,{isBeforeFirstMessage:!1}),',
    ]
)


def write_source_artifact(tmp_path, version="2.1.0"):
    fixture = build_bun_fixture(
        platform="elf",
        module_struct_size=52,
        modules=[{"name": "src/cli.js", "content": ENTRY_JS}],
        entry_point_id=0,
    )
    path = tmp_path / "claude"
    path.write_bytes(fixture["buf"])
    sha256 = hashlib.sha256(fixture["buf"]).hexdigest()
    return NativeArtifact(
        version=version,
        platform="linux-x64",
        sha256=sha256,
        path=path,
        metadata={},
    )


def write_macho_source_artifact(tmp_path, version="2.1.0"):
    fixture = build_bun_fixture(
        platform="macho",
        module_struct_size=52,
        modules=[{"name": "src/cli.js", "content": ENTRY_JS}],
        entry_point_id=0,
    )
    path = tmp_path / "claude-macho"
    path.write_bytes(fixture["buf"])
    sha256 = hashlib.sha256(fixture["buf"]).hexdigest()
    return NativeArtifact(
        version=version,
        platform="darwin-arm64",
        sha256=sha256,
        path=path,
        metadata={},
    )


def read_entry(binary_path):
    data = Path(binary_path).read_bytes()
    info = parse_bun_binary(data)
    entry = info.modules[info.entry_point_id]
    return data[info.data_start + entry.cont_off : info.data_start + entry.cont_off + entry.cont_len].decode("utf-8")


def test_create_variant_writes_isolated_layout_wrapper_and_metadata(tmp_path):
    root = tmp_path / ".cc-extractor"
    artifact = write_source_artifact(tmp_path)
    original = artifact.path.read_bytes()

    result = create_variant(
        name="Zai Test",
        provider_key="zai",
        credential_env="Z_AI_API_KEY",
        root=root,
        source_artifact=artifact,
        force=True,
    )

    assert artifact.path.read_bytes() == original
    assert result.variant.variant_id == "zai-test"
    assert result.binary_path == root / "variants" / "zai-test" / "native" / "claude"
    assert result.wrapper_path == root / "bin" / "zai-test"
    assert (root / "variants" / "zai-test" / "config" / "settings.json").exists()
    assert (root / "variants" / "zai-test" / "config" / ".claude.json").exists()
    assert (root / "variants" / "zai-test" / "tweakcc" / "config.json").exists()
    assert doctor_variant("zai-test", root=root)[0]["ok"] is True

    entry_js = read_entry(result.binary_path)
    assert "Zai Cloud variant" in entry_js
    assert "cc-mirror:provider-overlay start" in entry_js
    assert 'case"zai-variant"' in entry_js

    wrapper = result.wrapper_path.read_text(encoding="utf-8")
    assert "CLAUDE_CONFIG_DIR" in wrapper
    assert "${Z_AI_API_KEY:?Set Z_AI_API_KEY for variant zai-test}" in wrapper
    assert "ANTHROPIC_API_KEY=\"${Z_AI_API_KEY}\"" in wrapper
    assert scan_variants(root)[0].variant_id == "zai-test"
    stage_names = [stage.name for stage in result.stages]
    assert "prepare directories" in stage_names
    assert {"patch binary", "extract patch repack"} & set(stage_names)
    assert "write setup config" in stage_names
    assert all(stage.status == "ok" for stage in result.stages)

    settings = json.loads((root / "variants" / "zai-test" / "config" / "settings.json").read_text(encoding="utf-8"))
    claude_config = json.loads((root / "variants" / "zai-test" / "config" / ".claude.json").read_text(encoding="utf-8"))
    assert "mcp__web_reader__webReader" in settings["permissions"]["deny"]
    assert sorted(claude_config["mcpServers"]) == ["web-reader", "web-search-prime", "zai-mcp-server", "zread"]
    assert claude_config["mcpServers"]["web-reader"]["headers"] == {"Authorization": "Bearer Enter your API key"}


def test_macos_grow_skip_uses_unpacked_node_runtime(tmp_path, monkeypatch):
    import cc_extractor.variants as variants_module

    root = tmp_path / ".cc-extractor"
    artifact = write_macho_source_artifact(tmp_path)
    unpack_calls = []

    def fake_apply_patches(inputs):
        return SimpleNamespace(
            ok=True,
            skipped_reason="macho-grow-not-supported",
            missing_prompt_keys=[],
            resigned=False,
        )

    def fake_unpack_and_patch(**kwargs):
        unpack_calls.append(kwargs)
        unpacked_dir = Path(kwargs["unpacked_dir"])
        entry_path = unpacked_dir / "src" / "cli.js"
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        entry_path.write_text('const version="2.1.123 (Claude Code)";', encoding="latin1")
        (unpacked_dir / "package.json").write_text("{}", encoding="utf-8")
        (unpacked_dir / "node_modules").mkdir()
        return SimpleNamespace(
            entry_path=str(entry_path),
            patch=SimpleNamespace(
                theme_replaced=2,
                prompt_replaced=["webfetch"],
                prompt_missing=[],
            ),
        )

    monkeypatch.setattr(variants_module, "apply_patches", fake_apply_patches)
    monkeypatch.setattr(variants_module, "unpack_and_patch", fake_unpack_and_patch)

    result = create_variant(
        name="Mac Zai",
        provider_key="zai",
        credential_env="Z_AI_API_KEY",
        tweaks=["themes", "prompt-overlays"],
        root=root,
        source_artifact=artifact,
        force=True,
    )

    manifest = result.variant.manifest
    entry_path = Path(manifest["paths"]["entryPath"])
    wrapper = result.wrapper_path.read_text(encoding="utf-8")

    assert manifest["runtime"] == "node"
    assert manifest["paths"]["unpackedDir"] == str(root / "variants" / "mac-zai" / "unpacked")
    assert entry_path.read_text(encoding="latin1") == 'const version="2.1.123 (Claude Code)";'
    assert unpack_calls[0]["pristine_binary_path"] == str(artifact.path)
    assert "NODE_BIN=\"${NODE:-node}\"" in wrapper
    assert 'exec "$NODE_BIN" "$ENTRY_PATH" "$@"' in wrapper
    assert doctor_variant("mac-zai", root=root)[0]["ok"] is True
    assert manifest["patchResults"]["appliedTweaks"] == [
        "themes",
        "prompt-overlays",
    ]


def test_macos_regex_tweak_uses_unpacked_node_runtime_not_in_place_binary_patch(tmp_path, monkeypatch):
    import cc_extractor.variants as variants_module

    root = tmp_path / ".cc-extractor"
    artifact = write_macho_source_artifact(tmp_path)
    unpack_calls = []

    def fail_apply_patches(_inputs):
        raise AssertionError("regex-only tweaks should not use in-place binary patching")

    def fake_unpack_and_patch(**kwargs):
        unpack_calls.append(kwargs)
        unpacked_dir = Path(kwargs["unpacked_dir"])
        entry_path = unpacked_dir / "src" / "cli.js"
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        entry_path.write_text(ENTRY_JS, encoding="latin1")
        (unpacked_dir / "package.json").write_text("{}", encoding="utf-8")
        (unpacked_dir / "node_modules").mkdir()
        return SimpleNamespace(
            entry_path=str(entry_path),
            patch=SimpleNamespace(
                theme_replaced=0,
                prompt_replaced=[],
                prompt_missing=[],
            ),
        )

    monkeypatch.setattr(variants_module, "apply_patches", fail_apply_patches)
    monkeypatch.setattr(variants_module, "unpack_and_patch", fake_unpack_and_patch)

    result = create_variant(
        name="Mac Banner",
        provider_key="ccrouter",
        tweaks=["hide-startup-banner"],
        root=root,
        source_artifact=artifact,
        force=True,
    )

    entry_path = Path(result.variant.manifest["paths"]["entryPath"])
    entry_js = entry_path.read_text(encoding="latin1")
    stage_names = [stage.name for stage in result.stages]

    assert result.variant.manifest["runtime"] == "node"
    assert "unpack node runtime" in stage_names
    assert "patch binary" not in stage_names
    assert unpack_calls[0]["pristine_binary_path"] == str(artifact.path)
    assert "isBeforeFirstMessage" not in entry_js
    assert result.variant.manifest["patchResults"]["appliedTweaks"] == ["hide-startup-banner"]


def test_create_variant_build_error_includes_stages(tmp_path, monkeypatch):
    import cc_extractor.variants as variants_module

    root = tmp_path / ".cc-extractor"
    artifact = write_macho_source_artifact(tmp_path)

    def fake_apply_patches(_inputs):
        return SimpleNamespace(
            ok=False,
            reason="failed",
            detail="anchor missing",
            missing_prompt_keys=[],
            resigned=False,
        )

    monkeypatch.setattr(variants_module, "apply_patches", fake_apply_patches)

    with pytest.raises(VariantBuildError) as exc_info:
        create_variant(
            name="Broken Zai",
            provider_key="zai",
            credential_env="Z_AI_API_KEY",
            tweaks=["themes"],
            root=root,
            source_artifact=artifact,
            force=True,
        )

    err = exc_info.value
    assert err.stage == "patch binary"
    assert [stage.name for stage in err.stages] == ["prepare directories", "patch binary"]
    assert err.stages[-1].status == "failed"
    assert "anchor missing" in err.stages[-1].detail


def test_create_variant_stored_secret_is_not_in_metadata(tmp_path):
    root = tmp_path / ".cc-extractor"
    artifact = write_source_artifact(tmp_path)

    result = create_variant(
        name="Secret Zai",
        provider_key="zai",
        api_key="super-secret",
        store_secret=True,
        root=root,
        source_artifact=artifact,
        force=True,
    )

    variant_dir = root / "variants" / "secret-zai"
    metadata_text = (variant_dir / "variant.json").read_text(encoding="utf-8")
    settings_text = (variant_dir / "config" / "settings.json").read_text(encoding="utf-8")
    claude_config_text = (variant_dir / "config" / ".claude.json").read_text(encoding="utf-8")
    secrets_path = variant_dir / "secrets.env"

    assert "super-secret" not in metadata_text
    assert "super-secret" not in settings_text
    assert "super-secret" not in claude_config_text
    assert "Enter your API key" in claude_config_text
    assert "super-secret" in secrets_path.read_text(encoding="utf-8")
    assert oct(secrets_path.stat().st_mode & 0o777) == "0o600"
    assert result.variant.manifest["credential"]["mode"] == "stored"


def test_write_secrets_fchmods_existing_file_before_write(tmp_path, monkeypatch):
    secrets_path = tmp_path / "secrets.env"
    secrets_path.write_text("old\n", encoding="utf-8")
    secrets_path.chmod(0o644)
    calls = []
    real_fchmod = wrapper_module.os.fchmod

    def tracked_fchmod(fd, mode):
        calls.append(mode)
        return real_fchmod(fd, mode)

    monkeypatch.setattr(wrapper_module.os, "fchmod", tracked_fchmod)

    write_secrets(secrets_path, {"ANTHROPIC_API_KEY": "secret"})

    assert calls == [0o600]
    assert oct(secrets_path.stat().st_mode & 0o777) == "0o600"
    assert "secret" in secrets_path.read_text(encoding="utf-8")


def test_write_wrapper_rejects_unsafe_env_key(tmp_path):
    manifest = {
        "id": "unsafe",
        "provider": {"key": "mirror"},
        "env": {"X; touch /tmp/pwn": "1"},
        "credential": {"mode": "none", "targets": []},
        "paths": {
            "root": str(tmp_path / "variant"),
            "wrapper": str(tmp_path / "bin" / "unsafe"),
            "configDir": str(tmp_path / "variant" / "config"),
            "tweakccDir": str(tmp_path / "variant" / "tweakcc"),
            "tmpDir": str(tmp_path / "variant" / "tmp"),
            "binary": str(tmp_path / "variant" / "native" / "claude"),
        },
    }

    with pytest.raises(ValueError, match="wrapper env key"):
        write_wrapper(manifest)


def test_apply_variant_rebuilds_from_saved_metadata(tmp_path, monkeypatch):
    import cc_extractor.variants as variants_module

    root = tmp_path / ".cc-extractor"
    artifact = write_source_artifact(tmp_path)
    create_variant(
        name="Zai Test",
        provider_key="zai",
        credential_env="Z_AI_API_KEY",
        root=root,
        source_artifact=artifact,
        force=True,
    )
    variant = load_variant("zai-test", root=root)
    Path(variant.manifest["paths"]["binary"]).write_bytes(b"broken")
    evil_bin = tmp_path / "evil-bin"
    variant.manifest["paths"]["binDir"] = str(evil_bin)
    variant.manifest["paths"]["wrapper"] = str(evil_bin / "zai-test")
    (variant.path / "variant.json").write_text(json.dumps(variant.manifest), encoding="utf-8")

    monkeypatch.setattr(variants_module, "_download_source_artifact", lambda version, root=None: artifact)
    rebuilt = apply_variant("zai-test", root=root)

    assert rebuilt.binary_path.read_bytes() != b"broken"
    assert rebuilt.wrapper_path == root / "bin" / "zai-test"
    assert not (evil_bin / "zai-test").exists()
    assert "Zai Cloud variant" in read_entry(rebuilt.binary_path)


def test_patch_entry_js_rejects_tampered_entrypoint(tmp_path):
    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()
    outside = tmp_path / "outside.js"
    outside.write_text(ENTRY_JS, encoding="utf-8")

    with pytest.raises(ValueError, match="entryPoint"):
        patch_entry_js(
            extract_dir,
            {"entryPoint": "../outside.js"},
            provider_key="mirror",
            tweak_ids=[],
        )


def test_remove_variant_requires_confirmation_and_removes_wrapper(tmp_path):
    root = tmp_path / ".cc-extractor"
    artifact = write_source_artifact(tmp_path)
    result = create_variant(
        name="Zai Test",
        provider_key="zai",
        credential_env="Z_AI_API_KEY",
        root=root,
        source_artifact=artifact,
        force=True,
    )

    with pytest.raises(ValueError, match="--yes"):
        remove_variant("zai-test", root=root)

    assert remove_variant("zai-test", yes=True, root=root) is True
    assert not result.wrapper_path.exists()
    assert scan_variants(root) == []


def test_remove_variant_ignores_tampered_manifest_wrapper(tmp_path):
    root = tmp_path / ".cc-extractor"
    variant_dir = root / "variants" / "fake"
    canonical_wrapper = root / "bin" / "fake"
    outside_wrapper = tmp_path / "outside-wrapper"
    variant_dir.mkdir(parents=True)
    canonical_wrapper.parent.mkdir(parents=True)
    canonical_wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
    outside_wrapper.write_text("do not delete\n", encoding="utf-8")
    manifest = {
        "schemaVersion": 1,
        "id": "fake",
        "name": "Fake",
        "provider": {"key": "mirror"},
        "source": {"version": "1.2.3"},
        "paths": {"wrapper": str(outside_wrapper)},
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
    }
    (variant_dir / "variant.json").write_text(json.dumps(manifest), encoding="utf-8")

    assert remove_variant("fake", yes=True, root=root) is True

    assert not canonical_wrapper.exists()
    assert outside_wrapper.exists()
    assert not variant_dir.exists()


def test_run_variant_ignores_tampered_manifest_wrapper(tmp_path):
    root = tmp_path / ".cc-extractor"
    variant_dir = root / "variants" / "fake"
    canonical_wrapper = root / "bin" / "fake"
    outside_wrapper = tmp_path / "outside-wrapper"
    output = tmp_path / "output.txt"
    variant_dir.mkdir(parents=True)
    canonical_wrapper.parent.mkdir(parents=True)
    canonical_wrapper.write_text(f"#!/bin/sh\necho canonical > {output}\n", encoding="utf-8")
    outside_wrapper.write_text(f"#!/bin/sh\necho tampered > {output}\n", encoding="utf-8")
    canonical_wrapper.chmod(0o755)
    outside_wrapper.chmod(0o755)
    manifest = {
        "schemaVersion": 1,
        "id": "fake",
        "name": "Fake",
        "provider": {"key": "mirror"},
        "source": {"version": "1.2.3"},
        "paths": {"wrapper": str(outside_wrapper)},
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
    }
    (variant_dir / "variant.json").write_text(json.dumps(manifest), encoding="utf-8")

    assert run_variant("fake", root=root) == 0

    assert output.read_text(encoding="utf-8") == "canonical\n"


def test_variant_cli_list_and_show_json(monkeypatch, tmp_path, capsys):
    from cc_extractor import __main__ as cli
    import sys

    class FakeVariant:
        manifest = {
            "schemaVersion": 1,
            "id": "fake",
            "name": "Fake",
            "provider": {"key": "mirror"},
            "source": {"version": "1.2.3"},
            "paths": {"wrapper": "/tmp/fake"},
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
        variant_id = "fake"

    monkeypatch.setattr(cli, "scan_variants", lambda: [FakeVariant()])
    old_argv = sys.argv
    sys.argv = ["cc-extractor", "variant", "list", "--json"]
    try:
        cli.main()
    finally:
        sys.argv = old_argv

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["id"] == "fake"


def test_variant_cli_create_show_doctor_and_remove(monkeypatch, tmp_path, capsys):
    from cc_extractor import __main__ as cli
    import sys

    calls = []

    class FakeVariant:
        manifest = {
            "schemaVersion": 1,
            "id": "fake",
            "name": "Fake",
            "provider": {"key": "zai"},
            "source": {"version": "1.2.3"},
            "paths": {"wrapper": str(tmp_path / "fake")},
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
        variant_id = "fake"

    class FakeResult:
        variant = FakeVariant()
        binary_path = tmp_path / "claude"
        wrapper_path = tmp_path / "fake"
        output_sha256 = "a" * 64
        applied_tweaks = ["themes"]
        skipped_tweaks = []
        missing_prompt_keys = []

    def fake_create_variant(**kwargs):
        calls.append(kwargs)
        return FakeResult()

    monkeypatch.setattr(cli, "create_variant", fake_create_variant)
    monkeypatch.setattr(cli, "load_variant", lambda name: FakeVariant())
    monkeypatch.setattr(cli, "doctor_variant", lambda name=None, all_variants=False: [{"id": "fake", "name": "Fake", "ok": True, "checks": []}])
    monkeypatch.setattr(cli, "remove_variant", lambda name, yes=False: yes)

    old_argv = sys.argv
    try:
        sys.argv = [
            "cc-extractor",
            "variant",
            "create",
            "--name",
            "Fake",
            "--provider",
            "zai",
            "--credential-env",
            "Z_AI_API_KEY",
            "--tweak",
            "themes",
            "--json",
        ]
        cli.main()
        create_payload = json.loads(capsys.readouterr().out)
        assert create_payload["id"] == "fake"
        assert calls[0]["provider_key"] == "zai"
        assert calls[0]["tweaks"] == ["themes"]

        sys.argv = ["cc-extractor", "variant", "show", "fake", "--json"]
        cli.main()
        assert json.loads(capsys.readouterr().out)["id"] == "fake"

        sys.argv = ["cc-extractor", "variant", "doctor", "fake", "--json"]
        cli.main()
        assert json.loads(capsys.readouterr().out)[0]["ok"] is True

        sys.argv = ["cc-extractor", "variant", "remove", "fake", "--yes"]
        cli.main()
        assert "Removed variant" in capsys.readouterr().out
    finally:
        sys.argv = old_argv
