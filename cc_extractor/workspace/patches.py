"""Patch package + patch profile loading, validation, and persistence."""

import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .._utils import make_kebab_id, safe_read_json as _safe_read_json, utc_now as _utc_now
from .models import PatchPackage, PatchProfile
from .paths import (
    PATCH_ID_RE,
    SEMVER_RE,
    ensure_workspace,
    patch_profile_path,
    read_json,
    workspace_root,
    write_json,
)


def patch_profile_id_from_name(name: str) -> str:
    return make_kebab_id(name, label="patch profile name")


def scan_patch_packages(root: Optional[os.PathLike] = None) -> List[PatchPackage]:
    base = workspace_root(root) / "patches" / "packages"
    packages: List[PatchPackage] = []
    if not base.exists():
        return packages

    for manifest_path in base.glob("*/*/patch.json"):
        try:
            packages.append(load_patch_package(manifest_path.parent))
        except ValueError:
            continue

    return sorted(packages, key=lambda item: (item.patch_id, item.version))


def scan_patch_profiles(root: Optional[os.PathLike] = None) -> List[PatchProfile]:
    base = workspace_root(root) / "patches" / "profiles"
    profiles: List[PatchProfile] = []
    if not base.exists():
        return profiles

    for manifest_path in base.glob("*.json"):
        try:
            profiles.append(load_patch_profile(manifest_path.stem, root=root))
        except ValueError:
            continue

    return sorted(profiles, key=lambda item: item.name.lower())


def load_patch_package(package_dir: os.PathLike) -> PatchPackage:
    package_dir = Path(package_dir)
    manifest_path = package_dir / "patch.json"
    if not manifest_path.exists():
        raise ValueError(f"No patch.json found in {package_dir}")

    manifest = read_json(manifest_path)
    validate_patch_package_manifest(manifest)
    return PatchPackage(
        patch_id=manifest["id"],
        version=manifest["version"],
        name=manifest["name"],
        path=package_dir,
        manifest=manifest,
    )


def load_patch_profile(profile_id: str, root: Optional[os.PathLike] = None) -> PatchProfile:
    path = patch_profile_path(profile_id, root=root)
    if not path.exists():
        raise ValueError(f"No patch profile found for {profile_id}")

    manifest = read_json(path)
    validate_patch_profile_manifest(manifest)
    if manifest["id"] != profile_id:
        raise ValueError("patch profile filename does not match id")
    return PatchProfile(
        profile_id=manifest["id"],
        name=manifest["name"],
        patches=list(manifest["patches"]),
        path=path,
        manifest=manifest,
    )


def save_patch_profile(
    name: str,
    patches: Sequence[Dict],
    root: Optional[os.PathLike] = None,
    profile_id: Optional[str] = None,
    overwrite: bool = False,
) -> PatchProfile:
    clean_name = _clean_profile_name(name)
    profile_id = profile_id or patch_profile_id_from_name(clean_name)
    path = patch_profile_path(profile_id, root=root)
    existing = _safe_read_json(path)
    if path.exists() and not overwrite:
        raise ValueError(f"Patch profile {profile_id} already exists")

    now = _utc_now()
    manifest = {
        "schemaVersion": 1,
        "id": profile_id,
        "name": clean_name,
        "patches": [_normalize_profile_patch_ref(ref) for ref in patches],
        "createdAt": existing.get("createdAt") if existing else now,
        "updatedAt": now,
    }
    validate_patch_profile_manifest(manifest)
    ensure_workspace(root)
    write_json(path, manifest)
    return load_patch_profile(profile_id, root=root)


def rename_patch_profile(
    profile_id: str,
    name: str,
    root: Optional[os.PathLike] = None,
) -> PatchProfile:
    profile = load_patch_profile(profile_id, root=root)
    clean_name = _clean_profile_name(name)
    new_id = patch_profile_id_from_name(clean_name)
    old_path = profile.path
    new_path = patch_profile_path(new_id, root=root)
    if new_id != profile.profile_id and new_path.exists():
        raise ValueError(f"Patch profile {new_id} already exists")

    manifest = dict(profile.manifest)
    manifest["id"] = new_id
    manifest["name"] = clean_name
    manifest["updatedAt"] = _utc_now()
    validate_patch_profile_manifest(manifest)
    write_json(new_path, manifest)
    if new_path != old_path and old_path.exists():
        old_path.unlink()
    return load_patch_profile(new_id, root=root)


def delete_patch_profile(profile_id: str, root: Optional[os.PathLike] = None) -> bool:
    path = patch_profile_path(profile_id, root=root)
    if not path.exists():
        return False
    path.unlink()
    return True


def validate_patch_package_manifest(manifest: Dict) -> None:
    if manifest.get("schemaVersion") != 1:
        raise ValueError("patch package schemaVersion must be 1")

    patch_id = manifest.get("id")
    if not isinstance(patch_id, str) or not PATCH_ID_RE.match(patch_id):
        raise ValueError("patch package id must be lower-kebab-case")

    version = manifest.get("version")
    if not isinstance(version, str) or not SEMVER_RE.match(version):
        raise ValueError("patch package version must be SemVer")

    name = manifest.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("patch package name must be a non-empty string")

    targets = manifest.get("targets")
    if not isinstance(targets, dict):
        raise ValueError("patch package targets must be an object")

    for key in ("claudeVersions", "platforms", "sourceSha256"):
        value = targets.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
            raise ValueError(f"patch package targets.{key} must be a list of non-empty strings")

    operations = manifest.get("operations")
    if not isinstance(operations, list):
        raise ValueError("patch package operations must be a list")


def validate_patch_profile_manifest(manifest: Dict) -> None:
    if manifest.get("schemaVersion") != 1:
        raise ValueError("patch profile schemaVersion must be 1")

    profile_id = manifest.get("id")
    if not isinstance(profile_id, str) or not PATCH_ID_RE.match(profile_id):
        raise ValueError("patch profile id must be lower-kebab-case")

    name = manifest.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("patch profile name must be a non-empty string")

    patches = manifest.get("patches")
    if not isinstance(patches, list) or not patches:
        raise ValueError("patch profile patches must be a non-empty list")

    for index, ref in enumerate(patches):
        if not isinstance(ref, dict):
            raise ValueError(f"patch profile patches[{index}] must be an object")
        _normalize_profile_patch_ref(ref)

    for field in ("createdAt", "updatedAt"):
        value = manifest.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"patch profile {field} must be a non-empty string")


def _clean_profile_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("patch profile name must be a non-empty string")
    return name.strip()


def _normalize_profile_patch_ref(ref: Dict) -> Dict:
    patch_id = ref.get("id")
    version = ref.get("version")
    if not isinstance(patch_id, str) or not PATCH_ID_RE.match(patch_id):
        raise ValueError("patch profile patch id must be lower-kebab-case")
    if not isinstance(version, str) or not SEMVER_RE.match(version):
        raise ValueError("patch profile patch version must be SemVer")
    return {"id": patch_id, "version": version}
