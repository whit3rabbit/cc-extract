import contextlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .bundler import pack_bundle
from .binary_patcher import PatchInputs, apply_patches
from .binary_patcher.codesign import try_adhoc_sign
from .binary_patcher.unpack_and_patch import unpack_and_patch
from .downloader import download_binary
from .extractor import extract_all
from .patcher import apply_patch
from .providers import (
    apply_provider_claude_config,
    build_provider_env,
    get_provider,
    list_providers,
    provider_default_variant_name,
    provider_patch_config,
    provider_prompt_overlays,
)
from .variant_tweaks import (
    DEFAULT_TWEAK_IDS,
    apply_variant_tweaks,
    env_for_tweaks,
    normalize_tweak_ids,
)
from .workspace import (
    NativeArtifact,
    PATCH_ID_RE,
    file_sha256,
    load_patch_profile,
    native_artifact_from_path,
    native_binary_filename,
    read_json,
    scan_patch_packages,
    workspace_root,
    write_json,
)


VARIANT_METADATA = "variant.json"
SECRETS_FILE = "secrets.env"


@dataclass
class Variant:
    variant_id: str
    name: str
    path: Path
    manifest: Dict


@dataclass
class VariantBuildResult:
    variant: Variant
    binary_path: Path
    wrapper_path: Path
    output_sha256: str
    applied_tweaks: List[str]
    skipped_tweaks: List[str]
    missing_prompt_keys: List[str]


@dataclass
class _BinaryTweakResult:
    applied: List[str]
    skipped: List[str]
    missing: List[str]


@dataclass
class _RuntimePatchResult:
    tweaks: _BinaryTweakResult
    sign_result: object
    runtime: str = "native"
    entry_path: Optional[str] = None


@dataclass
class _AlreadySigned:
    signed: bool = True
    reason: str = None
    detail: str = None


def variant_id_from_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("variant name must be a non-empty string")
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise ValueError("variant name must contain letters or numbers")
    if not PATCH_ID_RE.match(slug):
        raise ValueError("variant id must be lower-kebab-case")
    return slug


def variant_root(variant_id: str, root=None) -> Path:
    if not isinstance(variant_id, str) or not PATCH_ID_RE.match(variant_id):
        raise ValueError("variant id must be lower-kebab-case")
    return workspace_root(root) / "variants" / variant_id


def default_bin_dir(root=None) -> Path:
    return workspace_root(root) / "bin"


def list_variant_providers() -> List[Dict[str, object]]:
    providers = []
    for provider in list_providers():
        providers.append(
            {
                "key": provider.key,
                "label": provider.label,
                "description": provider.description,
                "baseUrl": provider.base_url,
                "authMode": provider.auth_mode,
                "requiresModelMapping": provider.requires_model_mapping,
                "credentialOptional": provider.credential_optional,
                "credentialEnv": provider.credential_env or "",
                "authTokenFallback": provider.auth_token_fallback or "",
                "noPromptPack": provider.no_prompt_pack,
                "models": dict(provider.models),
                "mcpServers": sorted(provider.mcp_servers),
                "settingsPermissionsDeny": list(provider.settings_permissions_deny),
                "tui": dict(provider.tui),
                "defaultVariantName": provider.default_variant_name or provider.key,
            }
        )
    return providers


def scan_variants(root=None) -> List[Variant]:
    base = workspace_root(root) / "variants"
    variants = []
    if not base.exists():
        return variants
    for metadata_path in base.glob(f"*/{VARIANT_METADATA}"):
        try:
            variants.append(load_variant(metadata_path.parent.name, root=root))
        except ValueError:
            continue
    return sorted(variants, key=lambda item: item.name.lower())


def load_variant(variant_id: str, root=None) -> Variant:
    path = variant_root(variant_id, root=root)
    metadata_path = path / VARIANT_METADATA
    if not metadata_path.exists():
        raise ValueError(f"No variant found for {variant_id}")
    manifest = read_json(metadata_path)
    validate_variant_manifest(manifest)
    if manifest["id"] != variant_id:
        raise ValueError("variant filename does not match id")
    return Variant(variant_id=manifest["id"], name=manifest["name"], path=path, manifest=manifest)


def validate_variant_manifest(manifest: Dict) -> None:
    if manifest.get("schemaVersion") != 1:
        raise ValueError("variant schemaVersion must be 1")
    variant_id = manifest.get("id")
    if not isinstance(variant_id, str) or not PATCH_ID_RE.match(variant_id):
        raise ValueError("variant id must be lower-kebab-case")
    if not isinstance(manifest.get("name"), str) or not manifest["name"].strip():
        raise ValueError("variant name must be a non-empty string")
    provider = manifest.get("provider")
    if not isinstance(provider, dict) or not isinstance(provider.get("key"), str):
        raise ValueError("variant provider must include key")
    source = manifest.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("version"), str):
        raise ValueError("variant source must include version")
    paths = manifest.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("variant paths must be an object")
    runtime = manifest.get("runtime", "native")
    if runtime not in ("native", "node"):
        raise ValueError("variant runtime must be native or node")
    if runtime == "node" and paths and not isinstance(paths.get("entryPath"), str):
        raise ValueError("node variant paths must include entryPath")
    for field in ("createdAt", "updatedAt"):
        if not isinstance(manifest.get(field), str) or not manifest[field]:
            raise ValueError(f"variant {field} must be a non-empty string")


def create_variant(
    *,
    name: Optional[str] = None,
    provider_key: str,
    claude_version: str = "latest",
    patch_profile_id: Optional[str] = None,
    tweaks: Optional[Iterable[str]] = None,
    credential_env: Optional[str] = None,
    api_key: Optional[str] = None,
    store_secret: bool = False,
    bin_dir: Optional[os.PathLike] = None,
    force: bool = False,
    model_overrides: Optional[Dict[str, str]] = None,
    extra_env: Optional[List[str]] = None,
    tweak_options: Optional[Dict[str, str]] = None,
    root=None,
    source_artifact: Optional[NativeArtifact] = None,
) -> VariantBuildResult:
    provider = get_provider(provider_key)
    name = name or provider_default_variant_name(provider_key)
    variant_id = variant_id_from_name(name)
    path = variant_root(variant_id, root=root)
    if path.exists() and not force:
        raise ValueError(f"Variant {variant_id} already exists")

    provider_env = build_provider_env(
        provider_key,
        api_key=api_key,
        credential_env=credential_env,
        store_secret=store_secret,
        model_overrides=model_overrides,
        extra_env=extra_env,
    )
    tweak_ids = normalize_tweak_ids(tweaks or DEFAULT_TWEAK_IDS)
    safe_env = dict(provider_env.env)
    safe_env.update(env_for_tweaks(tweak_ids, tweak_options))
    now = _utc_now()
    existing = _safe_read_json(path / VARIANT_METADATA)
    patch_refs = _patch_refs_for_profile(patch_profile_id, root=root)

    manifest = {
        "schemaVersion": 1,
        "id": variant_id,
        "name": name.strip(),
        "provider": {
            "key": provider.key,
            "label": provider.label,
        },
        "source": {
            "version": claude_version or "latest",
        },
        "patchProfile": patch_profile_id,
        "patches": patch_refs,
        "tweaks": tweak_ids,
        "tweakOptions": dict(tweak_options or {}),
        "modelOverrides": dict(model_overrides or {}),
        "env": safe_env,
        "credential": provider_env.credential,
        "paths": {},
        "createdAt": existing.get("createdAt") if existing else now,
        "updatedAt": now,
    }
    validate_variant_manifest(manifest)

    path.mkdir(parents=True, exist_ok=True)
    if provider_env.secret_env:
        _write_secrets(path / SECRETS_FILE, provider_env.secret_env)
        manifest["credential"] = dict(manifest["credential"])
        manifest["credential"]["secretsPath"] = str(path / SECRETS_FILE)
    elif (path / SECRETS_FILE).exists():
        (path / SECRETS_FILE).unlink()

    return _build_variant_from_manifest(
        manifest,
        root=root,
        bin_dir=Path(bin_dir) if bin_dir is not None else default_bin_dir(root),
        source_artifact=source_artifact,
    )


def apply_variant(variant_id: str, *, claude_version: Optional[str] = None, root=None) -> VariantBuildResult:
    variant = load_variant(variant_id, root=root)
    manifest = dict(variant.manifest)
    if claude_version:
        manifest["source"] = dict(manifest["source"])
        manifest["source"]["version"] = claude_version
    manifest["updatedAt"] = _utc_now()
    return _build_variant_from_manifest(manifest, root=root, bin_dir=Path(manifest["paths"].get("binDir") or default_bin_dir(root)))


def update_variants(name: Optional[str] = None, *, all_variants: bool = False, claude_version: Optional[str] = None, root=None) -> List[VariantBuildResult]:
    if all_variants:
        return [apply_variant(variant.variant_id, claude_version=claude_version, root=root) for variant in scan_variants(root)]
    if not name:
        raise ValueError("Pass a variant name or --all")
    return [apply_variant(variant_id_from_name(name), claude_version=claude_version, root=root)]


def remove_variant(name: str, *, yes: bool = False, root=None) -> bool:
    if not yes:
        raise ValueError("Pass --yes to remove a variant")
    variant_id = variant_id_from_name(name)
    try:
        variant = load_variant(variant_id, root=root)
    except ValueError:
        return False
    wrapper_path = Path(variant.manifest.get("paths", {}).get("wrapper", ""))
    if wrapper_path.exists():
        wrapper_path.unlink()
    shutil.rmtree(variant.path)
    return True


def doctor_variant(name: Optional[str] = None, *, all_variants: bool = False, root=None) -> List[Dict[str, object]]:
    variants = scan_variants(root) if all_variants or name is None else [load_variant(variant_id_from_name(name), root=root)]
    reports = []
    for variant in variants:
        paths = variant.manifest.get("paths", {})
        runtime = variant.manifest.get("runtime", "native")
        binary = Path(paths.get("binary", ""))
        wrapper = Path(paths.get("wrapper", ""))
        config = Path(paths.get("configDir", "")) / "settings.json"
        secrets_path = variant.path / SECRETS_FILE
        checks = [
            {"name": "wrapper", "ok": wrapper.is_file(), "path": str(wrapper)},
            {"name": "settings", "ok": config.is_file(), "path": str(config)},
        ]
        if runtime == "node":
            entry = Path(paths.get("entryPath", ""))
            unpacked_dir = Path(paths.get("unpackedDir", ""))
            checks.extend(
                [
                    {"name": "binary", "ok": binary.is_file(), "path": str(binary)},
                    {"name": "node-entry", "ok": entry.is_file(), "path": str(entry)},
                    {"name": "package-json", "ok": (unpacked_dir / "package.json").is_file(), "path": str(unpacked_dir / "package.json")},
                    {"name": "node-modules", "ok": (unpacked_dir / "node_modules").is_dir(), "path": str(unpacked_dir / "node_modules")},
                ]
            )
        else:
            checks.append({"name": "binary", "ok": binary.is_file(), "path": str(binary)})
        if variant.manifest.get("credential", {}).get("mode") == "stored":
            checks.append({"name": "secrets", "ok": secrets_path.is_file(), "path": str(secrets_path)})
            if secrets_path.exists() and os.name != "nt":
                checks.append({"name": "secrets-mode", "ok": oct(secrets_path.stat().st_mode & 0o777) == "0o600", "path": str(secrets_path)})
        ok = all(check["ok"] for check in checks)
        reports.append({"id": variant.variant_id, "name": variant.name, "ok": ok, "checks": checks})
    return reports


def run_variant(name: str, args: Optional[List[str]] = None, root=None) -> int:
    variant = load_variant(variant_id_from_name(name), root=root)
    wrapper = Path(variant.manifest.get("paths", {}).get("wrapper", ""))
    if not wrapper.exists():
        raise ValueError(f"Variant wrapper is missing: {wrapper}")
    result = subprocess.run([str(wrapper), *(args or [])], check=False)
    return result.returncode


def _build_variant_from_manifest(
    manifest: Dict,
    *,
    root=None,
    bin_dir: Path,
    source_artifact: Optional[NativeArtifact] = None,
) -> VariantBuildResult:
    variant_id = manifest["id"]
    variant_dir = variant_root(variant_id, root=root)
    native_dir = variant_dir / "native"
    unpacked_dir = variant_dir / "unpacked"
    config_dir = variant_dir / "config"
    tweakcc_dir = variant_dir / "tweakcc"
    tmp_dir = variant_dir / "tmp"
    for path in (native_dir, config_dir, tweakcc_dir, tmp_dir, bin_dir):
        path.mkdir(parents=True, exist_ok=True)

    if source_artifact is None:
        source_artifact = _download_source_artifact(manifest["source"]["version"], root=root)
    binary_name = native_binary_filename(source_artifact.platform)
    output_binary = native_dir / binary_name
    runtime = "native"
    entry_path = None

    if _can_use_in_place_variant_patch(source_artifact, manifest):
        runtime_result = _copy_patch_or_unpack_variant_binary(
            source_artifact,
            output_binary,
            unpacked_dir,
            provider_key=manifest["provider"]["key"],
            tweak_ids=manifest.get("tweaks", []),
        )
        tweak_result = runtime_result.tweaks
        sign_result = runtime_result.sign_result
        runtime = runtime_result.runtime
        entry_path = runtime_result.entry_path
    else:
        with tempfile.TemporaryDirectory(prefix="variant-build-", dir=str(tmp_dir)) as temp_name:
            temp_root = Path(temp_name)
            extract_dir = temp_root / "bundle"
            staged_output = temp_root / binary_name
            manifest_data = extract_all(
                str(source_artifact.path),
                str(extract_dir),
                source_version=source_artifact.version,
            )
            _apply_patch_refs(extract_dir, manifest.get("patches", []), source_artifact, root=root)
            tweak_result = _patch_entry_js(
                extract_dir,
                manifest_data,
                provider_key=manifest["provider"]["key"],
                tweak_ids=manifest.get("tweaks", []),
            )
            pack_bundle(str(extract_dir), str(staged_output), str(source_artifact.path))
            shutil.move(str(staged_output), str(output_binary))
            if os.name != "nt":
                os.chmod(output_binary, 0o755)
            sign_result = try_adhoc_sign(str(output_binary))

    output_sha256 = file_sha256(output_binary)
    manifest = dict(manifest)
    manifest["runtime"] = runtime
    manifest["source"] = {
        "version": source_artifact.version,
        "platform": source_artifact.platform,
        "sha256": source_artifact.sha256,
        "path": str(source_artifact.path),
    }
    manifest["outputSha256"] = output_sha256
    manifest["paths"] = {
        "root": str(variant_dir),
        "binary": str(output_binary),
        "unpackedDir": str(unpacked_dir),
        "configDir": str(config_dir),
        "tweakccDir": str(tweakcc_dir),
        "tmpDir": str(tmp_dir),
        "binDir": str(bin_dir),
        "wrapper": str(bin_dir / variant_id),
    }
    if entry_path:
        manifest["paths"]["entryPath"] = str(entry_path)
        manifest["entrySha256"] = file_sha256(Path(entry_path))
    else:
        manifest.pop("entrySha256", None)
    manifest["patchResults"] = {
        "appliedTweaks": tweak_result.applied,
        "skippedTweaks": tweak_result.skipped,
        "missingPromptKeys": tweak_result.missing,
    }
    manifest["codesign"] = {
        "signed": sign_result.signed,
        "reason": sign_result.reason,
        "detail": sign_result.detail,
    }
    _write_variant_config(manifest)
    wrapper_path = _write_wrapper(manifest)
    manifest["paths"]["wrapper"] = str(wrapper_path)
    manifest["updatedAt"] = _utc_now()
    write_json(variant_dir / VARIANT_METADATA, manifest)
    variant = load_variant(variant_id, root=root)
    return VariantBuildResult(
        variant=variant,
        binary_path=output_binary,
        wrapper_path=wrapper_path,
        output_sha256=output_sha256,
        applied_tweaks=tweak_result.applied,
        skipped_tweaks=tweak_result.skipped,
        missing_prompt_keys=tweak_result.missing,
    )


def _download_source_artifact(version: str, root=None) -> NativeArtifact:
    requested = _resolve_source_version(version, root=root)
    with _workspace_env(root):
        path = download_binary(requested)
    artifact = native_artifact_from_path(path, root=root)
    if artifact is None:
        artifact = native_artifact_from_path(Path(path).resolve(), root=root)
    if artifact is None:
        raise ValueError(f"Downloaded binary was not found in workspace: {path}")
    return artifact


def _resolve_source_version(version: str, root=None) -> str:
    version = version or "latest"
    if version != "stable":
        return version
    index_path = workspace_root(root) / "download-index.json"
    index = _safe_read_json(index_path)
    stable = index.get("binary", {}).get("stable")
    if isinstance(stable, str) and stable:
        return stable
    raise ValueError("stable channel is not available in the download index")


def _patch_refs_for_profile(profile_id: Optional[str], root=None) -> List[Dict[str, str]]:
    if not profile_id:
        return []
    profile = load_patch_profile(profile_id, root=root)
    return list(profile.patches)


def _apply_patch_refs(extract_dir: Path, refs: List[Dict[str, str]], source_artifact: NativeArtifact, root=None) -> None:
    if not refs:
        return
    packages = {(package.patch_id, package.version): package for package in scan_patch_packages(root)}
    for ref in refs:
        package = packages.get((ref["id"], ref["version"]))
        if package is None:
            raise ValueError(f"Missing patch package {ref['id']}@{ref['version']}")
        apply_patch(
            package.path,
            extract_dir,
            binary_path=source_artifact.path,
            source_version=source_artifact.version,
            source_platform=source_artifact.platform,
        )


def _patch_entry_js(extract_dir: Path, manifest_data: Dict, *, provider_key: str, tweak_ids: List[str]):
    entry = manifest_data.get("entryPoint")
    if not entry:
        manifest_path = extract_dir / ".bundle_manifest.json"
        if manifest_path.exists():
            entry = read_json(manifest_path).get("entryPoint")
    if not entry:
        raise ValueError("Extracted bundle manifest did not include entryPoint")
    entry_path = extract_dir / entry
    if not entry_path.exists():
        raise ValueError(f"Entry JS not found in extracted bundle: {entry}")
    js = entry_path.read_text(encoding="utf-8")
    provider = get_provider(provider_key)
    result = apply_variant_tweaks(
        js,
        tweak_ids=tweak_ids,
        config=provider_patch_config(provider_key),
        overlays=provider_prompt_overlays(provider_key),
        provider_label=provider.label,
    )
    entry_path.write_text(result.js, encoding="utf-8")
    return result


def _can_use_in_place_variant_patch(source_artifact: NativeArtifact, manifest: Dict) -> bool:
    return (
        source_artifact.platform.startswith("darwin")
        and not manifest.get("patches")
    )


def _copy_patch_or_unpack_variant_binary(
    source_artifact: NativeArtifact,
    output_binary: Path,
    unpacked_dir: Path,
    *,
    provider_key: str,
    tweak_ids: List[str],
) -> _RuntimePatchResult:
    output_binary.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_artifact.path, output_binary)
    if os.name != "nt":
        os.chmod(output_binary, 0o755)

    config = provider_patch_config(provider_key) if "themes" in tweak_ids else {}
    overlays = provider_prompt_overlays(provider_key) if "prompt-overlays" in tweak_ids else None
    result = apply_patches(PatchInputs(binary_path=str(output_binary), config=config, overlays=overlays))
    if result.ok and result.skipped_reason == "macho-grow-not-supported" and (config or overlays):
        return _unpack_node_runtime_variant(
            source_artifact,
            output_binary,
            unpacked_dir,
            provider_key=provider_key,
            tweak_ids=tweak_ids,
            config=config,
            overlays=overlays,
        )
    if not result.ok:
        raise ValueError(f"binary patch failed: {result.reason}: {result.detail}")

    applied = []
    skipped = []
    missing = list(getattr(result, "missing_prompt_keys", []) or [])
    if result.skipped_reason:
        skipped.extend([tweak for tweak in ("themes", "prompt-overlays") if tweak in tweak_ids])
    else:
        if "themes" in tweak_ids and config:
            applied.append("themes")
        if "prompt-overlays" in tweak_ids and overlays:
            applied.append("prompt-overlays")

    unsupported = [
        tweak_id
        for tweak_id in tweak_ids
        if tweak_id not in {"themes", "prompt-overlays"}
    ]
    skipped.extend(tweak_id for tweak_id in unsupported if tweak_id not in skipped)
    sign_result = try_adhoc_sign(str(output_binary)) if not result.resigned else _AlreadySigned()
    return _RuntimePatchResult(
        tweaks=_BinaryTweakResult(applied, skipped, missing),
        sign_result=sign_result,
    )


def _unpack_node_runtime_variant(
    source_artifact: NativeArtifact,
    output_binary: Path,
    unpacked_dir: Path,
    *,
    provider_key: str,
    tweak_ids: List[str],
    config: Dict,
    overlays: Optional[Dict[str, str]],
) -> _RuntimePatchResult:
    provider = get_provider(provider_key)
    result = unpack_and_patch(
        pristine_binary_path=str(source_artifact.path),
        unpacked_dir=str(unpacked_dir),
        config=config,
        overlays=overlays,
    )
    applied = []
    skipped = []
    missing = list(result.patch.prompt_missing or [])

    if "themes" in tweak_ids:
        if result.patch.theme_replaced:
            applied.append("themes")
        else:
            skipped.append("themes")
    if "prompt-overlays" in tweak_ids:
        if result.patch.prompt_replaced:
            applied.append("prompt-overlays")
        else:
            skipped.append("prompt-overlays")

    remaining_tweaks = [tweak_id for tweak_id in tweak_ids if tweak_id not in {"themes", "prompt-overlays"}]
    if remaining_tweaks:
        entry_path = Path(result.entry_path)
        js = entry_path.read_text(encoding="latin1")
        extra = apply_variant_tweaks(
            js,
            tweak_ids=remaining_tweaks,
            config={},
            overlays={},
            provider_label=provider.label,
        )
        entry_path.write_text(extra.js, encoding="latin1")
        applied.extend(extra.applied)
        skipped.extend(extra.skipped)
        missing.extend(extra.missing)

    return _RuntimePatchResult(
        tweaks=_BinaryTweakResult(applied, skipped, missing),
        sign_result=_AlreadySigned(),
        runtime="node",
        entry_path=result.entry_path,
    )


def _write_variant_config(manifest: Dict) -> None:
    paths = manifest["paths"]
    env = dict(manifest.get("env", {}))
    write_json(Path(paths["configDir"]) / "settings.json", {"env": env})
    apply_provider_claude_config(
        manifest["provider"]["key"],
        paths["configDir"],
        credential_value=_stored_credential_value(manifest),
        read_json=read_json,
        write_json=write_json,
    )
    tweak_config = provider_patch_config(manifest["provider"]["key"])
    tweak_config["ccInstallationPath"] = paths["binary"]
    tweak_config["lastModified"] = _utc_now()
    write_json(Path(paths["tweakccDir"]) / "config.json", tweak_config)


def _stored_credential_value(manifest: Dict) -> Optional[str]:
    credential = manifest.get("credential", {})
    if credential.get("mode") != "stored":
        return None
    secrets_path = credential.get("secretsPath") or str(Path(manifest["paths"]["root"]) / SECRETS_FILE)
    secrets = _read_secret_exports(Path(secrets_path))
    if not secrets:
        return None

    provider = get_provider(manifest["provider"]["key"])
    preferred = [provider.credential_env, *credential.get("targets", [])]
    for key in preferred:
        if key and secrets.get(key):
            return secrets[key]
    return None


def _read_secret_exports(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            parts = shlex.split(line)
        except ValueError:
            continue
        if len(parts) != 2 or parts[0] != "export" or "=" not in parts[1]:
            continue
        key, value = parts[1].split("=", 1)
        if key:
            result[key] = value
    return result


def _write_wrapper(manifest: Dict) -> Path:
    paths = manifest["paths"]
    wrapper_path = Path(paths["wrapper"])
    variant_dir = Path(paths["root"])
    lines = [
        "#!/bin/sh",
        "set -eu",
        f"VARIANT_ROOT={shlex.quote(str(variant_dir))}",
        f"export CLAUDE_CONFIG_DIR={shlex.quote(paths['configDir'])}",
        f"export TWEAKCC_CONFIG_DIR={shlex.quote(paths['tweakccDir'])}",
        f"export CLAUDE_CODE_TMPDIR={shlex.quote(paths['tmpDir'])}",
        'export DISABLE_AUTOUPDATER="${DISABLE_AUTOUPDATER:-1}"',
        'export DISABLE_AUTO_MIGRATE_TO_NATIVE="${DISABLE_AUTO_MIGRATE_TO_NATIVE:-1}"',
    ]
    for key, value in sorted(manifest.get("env", {}).items()):
        lines.append(f"export {key}={shlex.quote(str(value))}")
    credential = manifest.get("credential", {})
    if credential.get("mode") == "stored":
        lines.append('if [ -f "$VARIANT_ROOT/secrets.env" ]; then . "$VARIANT_ROOT/secrets.env"; fi')
    elif credential.get("mode") == "env":
        source = credential.get("source")
        targets = credential.get("targets", [])
        lines.append(f": ${{{source}:?Set {source} for variant {manifest['id']}}}")
        for target in targets:
            lines.append(f"export {target}=\"${{{source}}}\"")
    if manifest.get("runtime", "native") == "node":
        lines.extend(
            [
                'NODE_BIN="${NODE:-node}"',
                "_NODE_USING_PROBE='using x = { [Symbol.dispose]() {} };'",
                '_node_supports_using() { "$1" --input-type=module -e "$_NODE_USING_PROBE" >/dev/null 2>&1; }',
                'if ! _node_supports_using "$NODE_BIN"; then',
                '  for nvm_root in "${NVM_DIR:-}" "${HOME:-}/.nvm"; do',
                '    [ -n "$nvm_root" ] || continue',
                '    [ -d "$nvm_root/versions/node" ] || continue',
                '    for candidate in "$nvm_root"/versions/node/v*/bin/node; do',
                '      if [ -x "$candidate" ] && _node_supports_using "$candidate"; then NODE_BIN="$candidate"; break 2; fi',
                "    done",
                "  done",
                "fi",
                'if ! _node_supports_using "$NODE_BIN"; then',
                '  echo "Variant node runtime requires Node with explicit resource management support. Set NODE=/path/to/node 24+." >&2',
                "  exit 127",
                "fi",
                f"ENTRY_PATH={shlex.quote(paths['entryPath'])}",
                'if [ ! -f "$ENTRY_PATH" ]; then echo "Variant entry is missing: $ENTRY_PATH" >&2; exit 127; fi',
                'exec "$NODE_BIN" "$ENTRY_PATH" "$@"',
            ]
        )
    else:
        lines.append(f"exec {shlex.quote(paths['binary'])} \"$@\"")
    wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    wrapper_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if os.name != "nt":
        os.chmod(wrapper_path, 0o755)
    return wrapper_path


def _write_secrets(path: Path, secret_env: Dict[str, str]) -> None:
    lines = [f"export {key}={shlex.quote(value)}" for key, value in sorted(secret_env.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if os.name != "nt":
        os.chmod(path, 0o600)


@contextlib.contextmanager
def _workspace_env(root):
    if root is None:
        yield
        return
    old_value = os.environ.get("CC_EXTRACTOR_WORKSPACE")
    os.environ["CC_EXTRACTOR_WORKSPACE"] = str(workspace_root(root))
    try:
        yield
    finally:
        if old_value is None:
            os.environ.pop("CC_EXTRACTOR_WORKSPACE", None)
        else:
            os.environ["CC_EXTRACTOR_WORKSPACE"] = old_value


def _safe_read_json(path: Path) -> Dict:
    try:
        if path.exists():
            return read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
