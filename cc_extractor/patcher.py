import hashlib
import json
from pathlib import Path

from .workspace import validate_patch_package_manifest

PATCH_MANIFEST = "patch.json"
SOURCE_METADATA = ".bundle_source.json"


def compute_sha256(path):
    sha256 = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def build_source_metadata(binary_path, source_version=None):
    metadata = {
        "binary_sha256": compute_sha256(binary_path),
    }
    if source_version is not None:
        metadata["source_version"] = source_version
    return metadata


def write_source_metadata(out_dir, binary_path, source_version=None):
    metadata = build_source_metadata(binary_path, source_version=source_version)
    metadata_path = Path(out_dir) / SOURCE_METADATA
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def load_source_metadata(extract_dir):
    metadata_path = Path(extract_dir) / SOURCE_METADATA
    if not metadata_path.exists():
        return None

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    checksum = metadata.get("binary_sha256")
    if not isinstance(checksum, str) or not checksum:
        raise ValueError(f"{SOURCE_METADATA} is missing binary_sha256")

    source_version = metadata.get("source_version")
    if source_version is not None and not isinstance(source_version, str):
        raise ValueError(f"{SOURCE_METADATA} has an invalid source_version")

    return metadata


def load_patch_manifest(patch_dir):
    manifest_path = Path(patch_dir) / PATCH_MANIFEST
    if not manifest_path.exists():
        raise ValueError(f"No {PATCH_MANIFEST} found in {patch_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") == 1:
        validate_patch_package_manifest(manifest)
        manifest = normalize_patch_package_manifest(manifest)

    for field in ("id", "description", "targets", "operations"):
        if field not in manifest:
            raise ValueError(f"{PATCH_MANIFEST} is missing required field {field!r}")

    if not isinstance(manifest["targets"], dict):
        raise ValueError("patch targets must be an object")
    if not isinstance(manifest["operations"], list):
        raise ValueError("patch operations must be a list")

    return manifest


def normalize_patch_package_manifest(manifest):
    targets = manifest.get("targets", {})
    return {
        "schemaVersion": manifest["schemaVersion"],
        "id": manifest["id"],
        "version": manifest["version"],
        "name": manifest["name"],
        "description": manifest.get("description") or manifest["name"],
        "targets": {
            "versions": targets.get("claudeVersions", []),
            "binary_sha256": targets.get("sourceSha256", []),
            "platforms": targets.get("platforms", []),
        },
        "operations": manifest.get("operations", []),
    }


def init_patch(patch_dir):
    patch_root = Path(patch_dir)
    patch_root.mkdir(parents=True, exist_ok=True)
    blocks_dir = patch_root / "blocks"
    patch_manifest_path = patch_root / PATCH_MANIFEST
    find_block_path = blocks_dir / "find_example.js"
    replace_block_path = blocks_dir / "replace_example.js"

    existing = [
        path for path in (patch_manifest_path, find_block_path, replace_block_path)
        if path.exists()
    ]
    if existing:
        names = ", ".join(str(path.relative_to(patch_root)) for path in existing)
        raise ValueError(f"Patch scaffold already exists in {patch_dir}: {names}")

    blocks_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "id": "example.patch",
        "description": "Example patch scaffold. Update paths, targets, and replacements.",
        "targets": {
            "versions": [],
            "binary_sha256": [],
        },
        "operations": [
            {
                "type": "replace_string",
                "path": "src/example.js",
                "find": "const featureEnabled = false;",
                "replace": "const featureEnabled = true;",
                "count": 1,
            },
            {
                "type": "replace_block",
                "path": "src/example.js",
                "find_file": "blocks/find_example.js",
                "replace_file": "blocks/replace_example.js",
                "count": 1,
            },
        ],
    }

    patch_manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    find_block_path.write_text(
        "function example() {\n"
        "  return 'before';\n"
        "}\n",
        encoding="utf-8",
    )
    replace_block_path.write_text(
        "function example() {\n"
        "  return 'after';\n"
        "}\n",
        encoding="utf-8",
    )

    print(f"[+] Created patch scaffold at {patch_root}")
    return patch_manifest_path


def apply_patch(
    patch_dir,
    extract_dir,
    check=False,
    binary_path=None,
    source_version=None,
    source_platform=None,
):
    patch_root = Path(patch_dir)
    extract_root = Path(extract_dir)
    manifest = load_patch_manifest(patch_root)
    source_metadata = load_source_metadata(extract_root)

    effective_checksum = compute_sha256(binary_path) if binary_path else (
        source_metadata.get("binary_sha256") if source_metadata else None
    )
    effective_version = source_version if source_version is not None else (
        source_metadata.get("source_version") if source_metadata else None
    )

    validate_patch_targets(
        manifest["targets"],
        effective_version=effective_version,
        effective_checksum=effective_checksum,
        effective_platform=source_platform,
    )

    pending_changes = {}
    applied_operations = []

    for index, operation in enumerate(manifest["operations"], start=1):
        target_path, updated_text, matches = apply_patch_operation(
            patch_root,
            extract_root,
            operation,
            pending_changes,
            index,
        )
        pending_changes[target_path] = updated_text
        applied_operations.append((operation["type"], target_path, matches))

    if check:
        print(f"[+] Patch check succeeded for {manifest['id']}")
        for op_type, target_path, matches in applied_operations:
            rel_path = target_path.relative_to(extract_root)
            print(f"    - {op_type}: {rel_path} ({matches} match{'es' if matches != 1 else ''})")
        return applied_operations

    for target_path, updated_text in pending_changes.items():
        target_path.write_text(updated_text, encoding="utf-8")

    print(f"[+] Applied patch {manifest['id']} to {extract_root}")
    for op_type, target_path, matches in applied_operations:
        rel_path = target_path.relative_to(extract_root)
        print(f"    - {op_type}: {rel_path} ({matches} match{'es' if matches != 1 else ''})")
    return applied_operations


def validate_patch_targets(
    targets,
    effective_version=None,
    effective_checksum=None,
    effective_platform=None,
):
    versions = targets.get("versions", [])
    checksums = targets.get("binary_sha256", [])
    platforms = targets.get("platforms", [])

    if not isinstance(versions, list) or any(not isinstance(item, str) or not item for item in versions):
        raise ValueError("patch targets.versions must be a list of non-empty strings")
    if not isinstance(checksums, list) or any(not isinstance(item, str) or not item for item in checksums):
        raise ValueError("patch targets.binary_sha256 must be a list of non-empty strings")
    if not isinstance(platforms, list) or any(not isinstance(item, str) or not item for item in platforms):
        raise ValueError("patch targets.platforms must be a list of non-empty strings")

    if versions:
        if not effective_version:
            raise ValueError(
                "Patch requires source version metadata. Re-extract with --source-version or pass --source-version."
            )
        if effective_version not in versions:
            raise ValueError(
                f"Patch targets versions {versions}, but source version is {effective_version!r}."
            )

    if checksums:
        if not effective_checksum:
            raise ValueError(
                "Patch requires binary checksum metadata. Re-extract from the source binary or pass --binary."
            )
        if effective_checksum not in checksums:
            raise ValueError("Patch does not target the provided binary checksum.")

    if platforms:
        if not effective_platform:
            raise ValueError("Patch requires source platform metadata.")
        if effective_platform not in platforms:
            raise ValueError(
                f"Patch targets platforms {platforms}, but source platform is {effective_platform!r}."
            )


def apply_patch_operation(patch_root, extract_root, operation, pending_changes, index):
    op_type = operation.get("type")
    if op_type not in {"replace_string", "replace_block"}:
        raise ValueError(f"Unsupported patch operation type at operations[{index - 1}]: {op_type!r}")

    rel_path = require_non_empty_string(operation.get("path"), f"operations[{index - 1}].path")
    target_path = extract_root / rel_path
    if not target_path.exists():
        raise ValueError(f"Patch target file does not exist: {rel_path}")

    current_text = pending_changes.get(target_path)
    if current_text is None:
        try:
            current_text = target_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Patch target file is not valid UTF-8: {rel_path}") from exc

    expected_count = operation.get("count", 1)
    if not isinstance(expected_count, int) or expected_count < 1:
        raise ValueError(f"operations[{index - 1}].count must be a positive integer")

    if op_type == "replace_string":
        find_text = require_non_empty_string(operation.get("find"), f"operations[{index - 1}].find")
        replace_text = require_string(operation.get("replace"), f"operations[{index - 1}].replace")
    else:
        find_file = require_non_empty_string(operation.get("find_file"), f"operations[{index - 1}].find_file")
        replace_file = require_non_empty_string(
            operation.get("replace_file"),
            f"operations[{index - 1}].replace_file",
        )
        find_text = read_patch_text(patch_root, find_file)
        replace_text = read_patch_text(patch_root, replace_file)

    matches = current_text.count(find_text)
    if matches == 0:
        raise ValueError(f"Patch operation {index} found no matches in {rel_path}")
    if matches != expected_count:
        raise ValueError(
            f"Patch operation {index} expected {expected_count} match(es) in {rel_path}, found {matches}"
        )

    updated_text = current_text.replace(find_text, replace_text, expected_count)
    return target_path, updated_text, matches


def read_patch_text(patch_root, rel_path):
    path = patch_root / rel_path
    if not path.exists():
        raise ValueError(f"Patch asset does not exist: {rel_path}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Patch asset is not valid UTF-8: {rel_path}") from exc


def require_non_empty_string(value, field_name):
    value = require_string(value, field_name)
    if not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def require_string(value, field_name):
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value
