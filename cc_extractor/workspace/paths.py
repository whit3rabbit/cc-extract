"""Constants, path builders, and basic file helpers."""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Dict, Optional, Tuple


WORKSPACE_DIR_NAME = ".cc-extractor"
ARTIFACT_METADATA = "artifact.json"
EXTRACTION_METADATA = "extraction.json"
PATCHED_METADATA = "patched.json"
TUI_SETTINGS = "tui-settings.json"

PATCH_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


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
        "variants",
        "bin",
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
        workspace_root(root) / "downloads" / "native" / version / platform_key / sha256 / filename
    )


def npm_download_path(
    version: str,
    sha256: str,
    tarball_name: str,
    root: Optional[os.PathLike] = None,
) -> Path:
    return workspace_root(root) / "downloads" / "npm" / version / sha256 / tarball_name


def extraction_paths(
    version: str,
    platform_key: str,
    source_sha256: str,
    root: Optional[os.PathLike] = None,
) -> Tuple[Path, Path]:
    parent = (
        workspace_root(root) / "extractions" / "native" / version / platform_key / source_sha256
    )
    return parent, parent / "bundle"


def extraction_metadata_path(bundle_path: os.PathLike) -> Path:
    return Path(bundle_path).parent / EXTRACTION_METADATA


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


def tui_settings_path(root: Optional[os.PathLike] = None) -> Path:
    return workspace_root(root) / TUI_SETTINGS


def patch_profile_path(profile_id: str, root: Optional[os.PathLike] = None) -> Path:
    if not isinstance(profile_id, str) or not PATCH_ID_RE.match(profile_id):
        raise ValueError("patch profile id must be lower-kebab-case")
    return workspace_root(root) / "patches" / "profiles" / f"{profile_id}.json"
