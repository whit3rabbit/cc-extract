"""Workspace state, paths, artifacts, patches, and TUI settings.

The package re-exports every symbol that the previous flat ``workspace.py``
module provided so that ``from cc_extractor.workspace import X`` imports keep
working unchanged across the codebase and tests.
"""

from .paths import (
    ARTIFACT_METADATA,
    EXTRACTION_METADATA,
    PATCH_ID_RE,
    PATCHED_METADATA,
    SEMVER_RE,
    TUI_SETTINGS,
    WORKSPACE_DIR_NAME,
    ensure_workspace,
    extraction_metadata_path,
    extraction_paths,
    file_sha256,
    native_binary_filename,
    native_download_path,
    npm_download_path,
    patch_profile_path,
    patched_output_path,
    read_json,
    short_sha,
    tui_settings_path,
    workspace_root,
    write_json,
)
from .models import (
    ExtractionArtifact,
    NativeArtifact,
    NpmArtifact,
    PatchPackage,
    PatchProfile,
    PatchedArtifact,
)
from .artifacts import (
    native_artifact_from_path,
    patchset_slug,
    scan_extractions,
    scan_native_downloads,
    scan_npm_downloads,
    store_native_download,
    store_npm_download,
    write_artifact_metadata,
    write_extraction_metadata,
    write_patched_metadata,
)
from .patches import (
    delete_patch_profile,
    load_patch_package,
    load_patch_profile,
    patch_profile_id_from_name,
    rename_patch_profile,
    save_patch_profile,
    scan_patch_packages,
    scan_patch_profiles,
    validate_patch_package_manifest,
    validate_patch_profile_manifest,
)
from .settings import load_tui_settings, save_tui_settings


__all__ = [
    # constants
    "ARTIFACT_METADATA",
    "EXTRACTION_METADATA",
    "PATCH_ID_RE",
    "PATCHED_METADATA",
    "SEMVER_RE",
    "TUI_SETTINGS",
    "WORKSPACE_DIR_NAME",
    # paths / I/O
    "ensure_workspace",
    "extraction_metadata_path",
    "extraction_paths",
    "file_sha256",
    "native_binary_filename",
    "native_download_path",
    "npm_download_path",
    "patch_profile_path",
    "patched_output_path",
    "read_json",
    "short_sha",
    "tui_settings_path",
    "workspace_root",
    "write_json",
    # dataclasses
    "ExtractionArtifact",
    "NativeArtifact",
    "NpmArtifact",
    "PatchPackage",
    "PatchProfile",
    "PatchedArtifact",
    # artifacts / scanners / storage
    "native_artifact_from_path",
    "patchset_slug",
    "scan_extractions",
    "scan_native_downloads",
    "scan_npm_downloads",
    "store_native_download",
    "store_npm_download",
    "write_artifact_metadata",
    "write_extraction_metadata",
    "write_patched_metadata",
    # patches
    "delete_patch_profile",
    "load_patch_package",
    "load_patch_profile",
    "patch_profile_id_from_name",
    "rename_patch_profile",
    "save_patch_profile",
    "scan_patch_packages",
    "scan_patch_profiles",
    "validate_patch_package_manifest",
    "validate_patch_profile_manifest",
    # settings
    "load_tui_settings",
    "save_tui_settings",
]
