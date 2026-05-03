"""Native/NPM/extraction artifact discovery and storage helpers."""

import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .._utils import safe_read_json as _safe_read_json, utc_now as _utc_now, version_sort_key as _version_sort_key
from .models import (
    ExtractionArtifact,
    NativeArtifact,
    NpmArtifact,
    PatchPackage,
)
from .paths import (
    ARTIFACT_METADATA,
    PATCHED_METADATA,
    extraction_metadata_path,
    file_sha256,
    native_download_path,
    npm_download_path,
    read_json,
    workspace_root,
    write_json,
)


def write_artifact_metadata(artifact_path: os.PathLike, payload: Dict) -> Path:
    path = Path(artifact_path).parent / ARTIFACT_METADATA
    metadata = dict(payload)
    metadata["createdAt"] = _utc_now()
    metadata["path"] = str(Path(artifact_path))
    write_json(path, metadata)
    return path


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
        version, platform_key, sha256, root=root, filename=filename,
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


def patchset_slug(packages: Sequence[PatchPackage]) -> str:
    if not packages:
        return "none"

    raw = "__".join(f"{package.patch_id}@{package.version}" for package in packages)
    slug = re.sub(r"[^A-Za-z0-9_.@-]+", "-", raw).strip("-")
    if len(slug) <= 96:
        return slug
    return f"{slug[:64]}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


# -- Scanners ----------------------------------------------------------------

def scan_native_downloads(root: Optional[os.PathLike] = None) -> List[NativeArtifact]:
    base = workspace_root(root) / "downloads" / "native"
    artifacts: List[NativeArtifact] = []
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
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        artifacts.append(
            NativeArtifact(
                version=metadata.get("version", version),
                platform=metadata.get("platform", platform_key),
                sha256=metadata.get("sha256", sha256),
                path=path,
                metadata=metadata,
                size=size,
            )
        )

    return sorted(
        artifacts,
        key=lambda item: (_version_sort_key(item.version), item.platform, item.sha256),
        reverse=True,
    )


def delete_native_download(
    artifact: NativeArtifact,
    root: Optional[os.PathLike] = None,
) -> bool:
    path = Path(artifact.path)
    try:
        base = (workspace_root(root) / "downloads" / "native").resolve()
        target = path.resolve()
        rel_parts = target.relative_to(base).parts
    except (OSError, ValueError) as exc:
        raise ValueError("native artifact path is outside workspace downloads") from exc

    if len(rel_parts) != 4 or target.name not in {"claude", "claude.exe"}:
        raise ValueError("not a native download artifact")

    artifact_dir = target.parent
    if not artifact_dir.exists():
        return False

    shutil.rmtree(artifact_dir)
    parent = artifact_dir.parent
    while parent != base:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent
    return True


def native_artifact_from_path(
    binary_path: os.PathLike,
    root: Optional[os.PathLike] = None,
) -> Optional[NativeArtifact]:
    try:
        target = Path(binary_path).resolve()
    except OSError:
        return None
    if target.name not in {"claude", "claude.exe"}:
        return None

    try:
        base = (workspace_root(root) / "downloads" / "native").resolve()
        rel_parts = target.relative_to(base).parts
    except (OSError, ValueError):
        return None
    if len(rel_parts) != 4:
        return None

    version, platform_key, sha256, _ = rel_parts
    metadata = _safe_read_json(target.parent / ARTIFACT_METADATA)
    if not metadata:
        return None
    try:
        size = target.stat().st_size
    except OSError:
        size = 0
    return NativeArtifact(
        version=metadata.get("version", version),
        platform=metadata.get("platform", platform_key),
        sha256=metadata.get("sha256", sha256),
        path=target,
        metadata=metadata,
        size=size,
    )


def scan_npm_downloads(root: Optional[os.PathLike] = None) -> List[NpmArtifact]:
    base = workspace_root(root) / "downloads" / "npm"
    artifacts: List[NpmArtifact] = []
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
    artifacts: List[ExtractionArtifact] = []
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
