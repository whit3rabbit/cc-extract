import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .bundler import pack_bundle
from .extractor import extract_all
from .patcher import apply_patch
from .workspace import (
    NativeArtifact,
    PatchPackage,
    ensure_workspace,
    file_sha256,
    native_binary_filename,
    patched_output_path,
    patchset_slug,
    write_patched_metadata,
)


@dataclass
class PatchWorkflowResult:
    output_path: Path
    metadata_path: Path
    output_sha256: str
    patchset: str


def apply_patch_packages_to_native(
    source_artifact: NativeArtifact,
    patch_packages: Sequence[PatchPackage],
    root=None,
) -> PatchWorkflowResult:
    if not patch_packages:
        raise ValueError("Select at least one patch package")

    workspace = ensure_workspace(root)
    tmp_root = workspace / "tmp"
    patchset = patchset_slug(patch_packages)

    with tempfile.TemporaryDirectory(prefix="patch-", dir=str(tmp_root)) as temp_dir:
        temp_root = Path(temp_dir)
        extract_dir = temp_root / "bundle"
        staged_output = temp_root / native_binary_filename(source_artifact.platform)

        extract_all(
            str(source_artifact.path),
            str(extract_dir),
            source_version=source_artifact.version,
        )

        for package in patch_packages:
            apply_patch(
                package.path,
                extract_dir,
                binary_path=source_artifact.path,
                source_version=source_artifact.version,
                source_platform=source_artifact.platform,
            )

        pack_bundle(str(extract_dir), str(staged_output), str(source_artifact.path))
        output_sha256 = file_sha256(staged_output)
        final_path = patched_output_path(
            source_artifact.version,
            source_artifact.platform,
            source_artifact.sha256,
            patchset,
            output_sha256,
            root=root,
            filename=source_artifact.path.name,
        )
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged_output), str(final_path))
        if os.name != "nt":
            os.chmod(final_path, 0o755)

    metadata_path = write_patched_metadata(
        final_path,
        source_artifact,
        patch_packages,
        output_sha256,
        patchset,
    )
    return PatchWorkflowResult(
        output_path=final_path,
        metadata_path=metadata_path,
        output_sha256=output_sha256,
        patchset=patchset,
    )
