import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


WORKSPACE_DIR_NAME = ".cc-extractor"
ARTIFACT_METADATA = "artifact.json"
EXTRACTION_METADATA = "extraction.json"
PATCHED_METADATA = "patched.json"

PATCH_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


@dataclass
class NativeArtifact:
    version: str
    platform: str
    sha256: str
    path: Path
    metadata: Dict


@dataclass
class NpmArtifact:
    version: str
    sha256: str
    path: Path
    metadata: Dict


@dataclass
class ExtractionArtifact:
    version: str
    platform: str
    source_sha256: str
    bundle_path: Path
    metadata: Dict


@dataclass
class PatchPackage:
    patch_id: str
    version: str
    name: str
    path: Path
    manifest: Dict


@dataclass
class PatchProfile:
    profile_id: str
    name: str
    patches: List[Dict]
    path: Path
    manifest: Dict


@dataclass
class PatchedArtifact:
    version: str
    platform: str
    source_sha256: str
    patchset: str
    output_sha256: str
    path: Path
    metadata: Dict


def workspace_root(root: Optional[os.PathLike] = None) -> Path:
    if root is not None:
        return Path(root)

    override = os.environ.get("CC_EXTRACTOR_WORKSPACE")
    if override:
        return Path(override).expanduser()

    return Path.cwd() / WORKSPACE_DIR_NAME


def ensure_workspace(root: Optional[os.PathLike] = None) -> Path:
    root_path = workspace_root(root)
    for rel_path in (
        "downloads/native",
        "downloads/npm",
        "extractions/native",
        "patches/packages",
        "patches/profiles",
        "patched/native",
        "tmp",
    ):
        (root_path / rel_path).mkdir(parents=True, exist_ok=True)
    return root_path


def file_sha256(path: os.PathLike) -> str:
    sha256 = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def short_sha(value: str) -> str:
    return value[:12]


def write_json(path: os.PathLike, payload: Dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: os.PathLike) -> Dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def native_binary_filename(platform_key: str) -> str:
    return "claude.exe" if platform_key.startswith("win32") else "claude"


def native_download_path(
    version: str,
    platform_key: str,
    sha256: str,
    root: Optional[os.PathLike] = None,
    filename: Optional[str] = None,
) -> Path:
    filename = filename or native_binary_filename(platform_key)
    return (
        workspace_root(root)
        / "downloads"
        / "native"
        / version
        / platform_key
        / sha256
        / filename
    )


def npm_download_path(
    version: str,
    sha256: str,
    tarball_name: str,
    root: Optional[os.PathLike] = None,
) -> Path:
    return workspace_root(root) / "downloads" / "npm" / version / sha256 / tarball_name


def store_native_download(
    staged_path: os.PathLike,
    version: str,
    platform_key: str,
    sha256: str,
    source_url: Optional[str] = None,
    root: Optional[os.PathLike] = None,
    filename: Optional[str] = None,
) -> Path:
    final_path = native_download_path(
        version,
        platform_key,
        sha256,
        root=root,
        filename=filename,
    )
    final_path.parent.mkdir(parents=True, exist_ok=True)
    staged_path = Path(staged_path)

    if final_path.exists() and file_sha256(final_path) == sha256:
        if staged_path.exists() and staged_path.resolve() != final_path.resolve():
            staged_path.unlink()
    else:
        shutil.move(str(staged_path), str(final_path))

    write_artifact_metadata(
        final_path,
        {
            "kind": "native",
            "version": version,
            "platform": platform_key,
            "sha256": sha256,
            "filename": final_path.name,
            "sourceUrl": source_url,
        },
    )
    return final_path


def store_npm_download(
    staged_path: os.PathLike,
    version: str,
    sha256: str,
    root: Optional[os.PathLike] = None,
) -> Path:
    staged_path = Path(staged_path)
    final_path = npm_download_path(version, sha256, staged_path.name, root=root)
    final_path.parent.mkdir(parents=True, exist_ok=True)

    if final_path.exists() and file_sha256(final_path) == sha256:
        if staged_path.exists() and staged_path.resolve() != final_path.resolve():
            staged_path.unlink()
    else:
        shutil.move(str(staged_path), str(final_path))

    write_artifact_metadata(
        final_path,
        {
            "kind": "npm",
            "version": version,
            "sha256": sha256,
            "filename": final_path.name,
        },
    )
    return final_path


def write_artifact_metadata(artifact_path: os.PathLike, payload: Dict) -> Path:
    path = Path(artifact_path).parent / ARTIFACT_METADATA
    metadata = dict(payload)
    metadata["createdAt"] = _utc_now()
    metadata["path"] = str(Path(artifact_path))
    write_json(path, metadata)
    return path


def extraction_paths(
    version: str,
    platform_key: str,
    source_sha256: str,
    root: Optional[os.PathLike] = None,
) -> Tuple[Path, Path]:
    parent = (
        workspace_root(root)
        / "extractions"
        / "native"
        / version
        / platform_key
        / source_sha256
    )
    return parent, parent / "bundle"


def extraction_metadata_path(bundle_path: os.PathLike) -> Path:
    return Path(bundle_path).parent / EXTRACTION_METADATA


def write_extraction_metadata(
    bundle_path: os.PathLike,
    source_path: os.PathLike,
    version: str,
    platform_key: str,
    source_sha256: str,
) -> Path:
    bundle_path = Path(bundle_path)
    metadata_path = extraction_metadata_path(bundle_path)
    manifest_path = bundle_path / ".bundle_manifest.json"
    module_count = None
    if manifest_path.exists():
        module_count = len(read_json(manifest_path).get("modules", []))

    payload = {
        "kind": "native-extraction",
        "version": version,
        "platform": platform_key,
        "sourceSha256": source_sha256,
        "sourcePath": str(source_path),
        "bundlePath": str(bundle_path),
        "moduleCount": module_count,
        "createdAt": _utc_now(),
    }
    write_json(metadata_path, payload)
    return metadata_path


def patched_output_path(
    version: str,
    platform_key: str,
    source_sha256: str,
    patchset: str,
    output_sha256: str,
    root: Optional[os.PathLike] = None,
    filename: Optional[str] = None,
) -> Path:
    filename = filename or native_binary_filename(platform_key)
    return (
        workspace_root(root)
        / "patched"
        / "native"
        / version
        / platform_key
        / source_sha256
        / patchset
        / output_sha256
        / filename
    )


def write_patched_metadata(
    output_path: os.PathLike,
    source_artifact: NativeArtifact,
    patch_packages: Sequence[PatchPackage],
    output_sha256: str,
    patchset: str,
) -> Path:
    payload = {
        "kind": "native-patched",
        "version": source_artifact.version,
        "platform": source_artifact.platform,
        "sourceSha256": source_artifact.sha256,
        "sourcePath": str(source_artifact.path),
        "outputSha256": output_sha256,
        "outputPath": str(output_path),
        "patchset": patchset,
        "patches": [
            {
                "id": package.patch_id,
                "version": package.version,
                "name": package.name,
                "path": str(package.path),
            }
            for package in patch_packages
        ],
        "createdAt": _utc_now(),
    }
    metadata_path = Path(output_path).parent / PATCHED_METADATA
    write_json(metadata_path, payload)
    return metadata_path


def scan_native_downloads(root: Optional[os.PathLike] = None) -> List[NativeArtifact]:
    base = workspace_root(root) / "downloads" / "native"
    artifacts = []
    if not base.exists():
        return artifacts

    for path in base.glob("*/*/*/*"):
        if not path.is_file() or path.name not in {"claude", "claude.exe"}:
            continue
        rel_parts = path.relative_to(base).parts
        if len(rel_parts) != 4:
            continue

        version, platform_key, sha256, _ = rel_parts
        metadata = _safe_read_json(path.parent / ARTIFACT_METADATA)
        artifacts.append(
            NativeArtifact(
                version=metadata.get("version", version),
                platform=metadata.get("platform", platform_key),
                sha256=metadata.get("sha256", sha256),
                path=path,
                metadata=metadata,
            )
        )

    return sorted(
        artifacts,
        key=lambda item: (_version_sort_key(item.version), item.platform, item.sha256),
        reverse=True,
    )


def native_artifact_from_path(
    binary_path: os.PathLike,
    root: Optional[os.PathLike] = None,
) -> Optional[NativeArtifact]:
    try:
        target = Path(binary_path).resolve()
    except OSError:
        return None

    for artifact in scan_native_downloads(root):
        try:
            if artifact.path.resolve() == target:
                return artifact
        except OSError:
            continue
    return None


def scan_npm_downloads(root: Optional[os.PathLike] = None) -> List[NpmArtifact]:
    base = workspace_root(root) / "downloads" / "npm"
    artifacts = []
    if not base.exists():
        return artifacts

    for path in base.glob("*/*/*"):
        if not path.is_file() or path.name == ARTIFACT_METADATA:
            continue
        rel_parts = path.relative_to(base).parts
        if len(rel_parts) != 3:
            continue

        version, sha256, _ = rel_parts
        metadata = _safe_read_json(path.parent / ARTIFACT_METADATA)
        artifacts.append(
            NpmArtifact(
                version=metadata.get("version", version),
                sha256=metadata.get("sha256", sha256),
                path=path,
                metadata=metadata,
            )
        )

    return sorted(
        artifacts,
        key=lambda item: (_version_sort_key(item.version), item.sha256),
        reverse=True,
    )


def scan_extractions(root: Optional[os.PathLike] = None) -> List[ExtractionArtifact]:
    base = workspace_root(root) / "extractions" / "native"
    artifacts = []
    if not base.exists():
        return artifacts

    for bundle_path in base.glob("*/*/*/bundle"):
        if not bundle_path.is_dir():
            continue
        rel_parts = bundle_path.relative_to(base).parts
        if len(rel_parts) != 4:
            continue
        version, platform_key, source_sha256, _ = rel_parts
        metadata = _safe_read_json(extraction_metadata_path(bundle_path))
        artifacts.append(
            ExtractionArtifact(
                version=metadata.get("version", version),
                platform=metadata.get("platform", platform_key),
                source_sha256=metadata.get("sourceSha256", source_sha256),
                bundle_path=bundle_path,
                metadata=metadata,
            )
        )

    return sorted(
        artifacts,
        key=lambda item: (_version_sort_key(item.version), item.platform, item.source_sha256),
        reverse=True,
    )


def scan_patch_packages(root: Optional[os.PathLike] = None) -> List[PatchPackage]:
    base = workspace_root(root) / "patches" / "packages"
    packages = []
    if not base.exists():
        return packages

    for manifest_path in base.glob("*/*/patch.json"):
        try:
            packages.append(load_patch_package(manifest_path.parent))
        except ValueError:
            continue

    return sorted(packages, key=lambda item: (item.patch_id, item.version))


def patch_profile_id_from_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("patch profile name must be a non-empty string")
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise ValueError("patch profile name must contain letters or numbers")
    return slug


def patch_profile_path(profile_id: str, root: Optional[os.PathLike] = None) -> Path:
    if not isinstance(profile_id, str) or not PATCH_ID_RE.match(profile_id):
        raise ValueError("patch profile id must be lower-kebab-case")
    return workspace_root(root) / "patches" / "profiles" / f"{profile_id}.json"


def scan_patch_profiles(root: Optional[os.PathLike] = None) -> List[PatchProfile]:
    base = workspace_root(root) / "patches" / "profiles"
    profiles = []
    if not base.exists():
        return profiles

    for manifest_path in base.glob("*.json"):
        try:
            profiles.append(load_patch_profile(manifest_path.stem, root=root))
        except ValueError:
            continue

    return sorted(profiles, key=lambda item: item.name.lower())


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


def patchset_slug(packages: Sequence[PatchPackage]) -> str:
    if not packages:
        return "none"

    raw = "__".join(f"{package.patch_id}@{package.version}" for package in packages)
    slug = re.sub(r"[^A-Za-z0-9_.@-]+", "-", raw).strip("-")
    if len(slug) <= 96:
        return slug
    return f"{slug[:64]}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _safe_read_json(path: Path) -> Dict:
    try:
        if path.exists():
            return read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return {}


def _version_sort_key(version: str) -> Tuple:
    parts = []
    for part in str(version).split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(-1)
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
