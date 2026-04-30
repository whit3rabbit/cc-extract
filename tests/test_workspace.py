import hashlib
import json

import pytest

from cc_extractor.extractor import extract_all
from cc_extractor.patch_workflow import apply_patch_packages_to_native
from cc_extractor.workspace import (
    ARTIFACT_METADATA,
    EXTRACTION_METADATA,
    delete_patch_profile,
    load_patch_package,
    load_patch_profile,
    rename_patch_profile,
    scan_native_downloads,
    scan_npm_downloads,
    scan_patch_profiles,
    save_patch_profile,
    store_native_download,
    store_npm_download,
    validate_patch_profile_manifest,
    workspace_root,
)
from tests.helpers.bun_fixture import build_bun_fixture


def write_patch_package(root, patch_id="replace-before", version="0.1.0"):
    package_dir = root / "patches" / "packages" / patch_id / version
    package_dir.mkdir(parents=True)
    manifest = {
        "schemaVersion": 1,
        "id": patch_id,
        "version": version,
        "name": "Replace Before",
        "targets": {
            "claudeVersions": ["1.2.3"],
            "platforms": ["darwin-arm64"],
            "sourceSha256": [],
        },
        "operations": [
            {
                "type": "replace_string",
                "path": "src/index.js",
                "find": "before",
                "replace": "after",
            }
        ],
    }
    (package_dir / "patch.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return package_dir


def test_workspace_root_defaults_to_repo_local_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert workspace_root() == tmp_path / ".cc-extractor"


def test_store_and_scan_native_download(tmp_path):
    root = tmp_path / ".cc-extractor"
    staged = tmp_path / "claude"
    staged.write_bytes(b"native-binary")
    sha256 = hashlib.sha256(b"native-binary").hexdigest()

    final_path = store_native_download(staged, "1.2.3", "darwin-arm64", sha256, root=root)

    assert final_path == root / "downloads" / "native" / "1.2.3" / "darwin-arm64" / sha256 / "claude"
    metadata = json.loads((final_path.parent / ARTIFACT_METADATA).read_text(encoding="utf-8"))
    assert metadata["version"] == "1.2.3"
    assert metadata["platform"] == "darwin-arm64"
    assert metadata["sha256"] == sha256

    artifacts = scan_native_downloads(root)
    assert len(artifacts) == 1
    assert artifacts[0].path == final_path
    assert artifacts[0].sha256 == sha256


def test_store_and_scan_npm_download(tmp_path):
    root = tmp_path / ".cc-extractor"
    staged = tmp_path / "anthropic-ai-claude-code-1.2.3.tgz"
    staged.write_bytes(b"npm-tarball")
    sha256 = hashlib.sha256(b"npm-tarball").hexdigest()

    final_path = store_npm_download(staged, "1.2.3", sha256, root=root)

    assert final_path == root / "downloads" / "npm" / "1.2.3" / sha256 / staged.name
    artifacts = scan_npm_downloads(root)
    assert len(artifacts) == 1
    assert artifacts[0].path == final_path


def test_extract_all_uses_central_extraction_for_central_download(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fixture = build_bun_fixture(
        platform="macho",
        modules=[{"name": "src/index.js", "content": "console.log('before');"}],
    )
    staged = tmp_path / "claude"
    staged.write_bytes(fixture["buf"])
    sha256 = hashlib.sha256(fixture["buf"]).hexdigest()
    source_path = store_native_download(staged, "1.2.3", "darwin-arm64", sha256)

    manifest = extract_all(str(source_path))

    bundle_path = (
        tmp_path
        / ".cc-extractor"
        / "extractions"
        / "native"
        / "1.2.3"
        / "darwin-arm64"
        / sha256
        / "bundle"
    )
    assert (bundle_path / ".bundle_manifest.json").exists()
    assert (bundle_path.parent / EXTRACTION_METADATA).exists()
    assert (bundle_path / "src/index.js").read_text(encoding="utf-8") == "console.log('before');"
    assert manifest["entryPoint"] == "src/index.js"

    reused_manifest = extract_all(str(source_path))
    assert reused_manifest["entryPoint"] == "src/index.js"


def test_patch_workflow_writes_patched_copy_without_mutating_download(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fixture = build_bun_fixture(
        platform="macho",
        modules=[{"name": "src/index.js", "content": "console.log('before');"}],
    )
    staged = tmp_path / "claude"
    staged.write_bytes(fixture["buf"])
    sha256 = hashlib.sha256(fixture["buf"]).hexdigest()
    source_path = store_native_download(staged, "1.2.3", "darwin-arm64", sha256)
    source_artifact = scan_native_downloads()[0]
    package = load_patch_package(write_patch_package(tmp_path / ".cc-extractor"))

    result = apply_patch_packages_to_native(source_artifact, [package])

    assert source_path.read_bytes() == fixture["buf"]
    assert result.output_path.exists()
    assert ".cc-extractor/patched/native/1.2.3/darwin-arm64" in str(result.output_path)
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["sourceSha256"] == sha256
    assert metadata["patches"][0]["id"] == "replace-before"

    roundtrip_dir = tmp_path / "roundtrip"
    extract_all(str(result.output_path), str(roundtrip_dir))
    assert (roundtrip_dir / "src/index.js").read_text(encoding="utf-8") == "console.log('after');"


def test_patch_profile_lifecycle_uses_workspace_json(tmp_path):
    root = tmp_path / ".cc-extractor"

    profile = save_patch_profile(
        "Focus Build",
        [{"id": "replace-before", "version": "0.1.0"}],
        root=root,
    )

    assert profile.profile_id == "focus-build"
    assert profile.path == root / "patches" / "profiles" / "focus-build.json"
    assert load_patch_profile("focus-build", root=root).name == "Focus Build"
    assert scan_patch_profiles(root)[0].profile_id == "focus-build"

    renamed = rename_patch_profile("focus-build", "Daily Build", root=root)

    assert renamed.profile_id == "daily-build"
    assert renamed.name == "Daily Build"
    assert not (root / "patches" / "profiles" / "focus-build.json").exists()
    assert delete_patch_profile("daily-build", root=root) is True
    assert scan_patch_profiles(root) == []


def test_patch_profile_validation_rejects_bad_schema():
    with pytest.raises(ValueError, match="schemaVersion"):
        validate_patch_profile_manifest({})

    with pytest.raises(ValueError, match="non-empty list"):
        validate_patch_profile_manifest(
            {
                "schemaVersion": 1,
                "id": "empty-profile",
                "name": "Empty Profile",
                "patches": [],
                "createdAt": "2026-01-01T00:00:00Z",
                "updatedAt": "2026-01-01T00:00:00Z",
            }
        )


def test_patch_profile_rename_refuses_id_collision(tmp_path):
    root = tmp_path / ".cc-extractor"
    save_patch_profile("Alpha", [{"id": "replace-before", "version": "0.1.0"}], root=root)
    save_patch_profile("Beta", [{"id": "replace-before", "version": "0.1.0"}], root=root)

    with pytest.raises(ValueError, match="already exists"):
        rename_patch_profile("alpha", "Beta", root=root)
