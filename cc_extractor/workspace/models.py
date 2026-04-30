"""Workspace artifact dataclasses (no I/O)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class NativeArtifact:
    version: str
    platform: str
    sha256: str
    path: Path
    metadata: Dict
    size: int = 0


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
