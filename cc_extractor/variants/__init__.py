"""Variant lifecycle (create / apply / update / remove / doctor / run).

The action layer lives in this ``__init__`` module so that test fixtures can
``monkeypatch.setattr`` externally-supplied helpers (``apply_patches``,
``unpack_and_patch``, ``download_binary``, ``_download_source_artifact``,
etc.) and have those patches propagate to the call sites.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .._utils import atomic_write_text_no_symlink, safe_read_json as _safe_read_json, utc_now as _utc_now
from ..binary_patcher import PatchInputs, apply_patches
from ..binary_patcher.codesign import try_adhoc_sign
from ..binary_patcher.unpack_and_patch import unpack_and_patch
from ..bundler import pack_bundle
from ..downloader import download_binary
from ..extractor import extract_all
from ..providers import (
    build_provider_env,
    get_provider,
    normalize_mcp_ids,
    provider_default_variant_name,
    provider_patch_config,
    provider_prompt_overlays,
)
from ..workspace import (
    NativeArtifact,
    file_sha256,
    native_artifact_from_path,
    native_binary_filename,
    read_json,
    workspace_root,
    write_json,
)
from .builder import (
    apply_patch_refs as _apply_patch_refs,
    can_use_in_place_variant_patch as _can_use_in_place_variant_patch,
    patch_entry_js as _patch_entry_js,
    patch_refs_for_profile as _patch_refs_for_profile,
    resolve_source_version as _resolve_source_version,
    workspace_env as _workspace_env,
)
from .model import (
    Variant,
    VariantBuildError,
    VariantBuildResult,
    VariantBuildStage,
    _AlreadySigned,
    _BinaryTweakResult,
    _RuntimePatchResult,
    default_bin_dir,
    list_variant_providers,
    validate_variant_manifest,
    variant_id_from_name,
    variant_root,
)
from .tweaks import (
    DEFAULT_TWEAK_IDS,
    ENV_TWEAK_IDS,
    apply_variant_tweaks,
    env_for_tweaks,
    normalize_tweak_ids,
)
from .wrapper import (
    SECRETS_FILE,
    SECRETS_FILE_MODE,
    validate_secret_file as _validate_secret_file,
    write_secrets as _write_secrets,
    write_variant_config as _write_variant_config,
    write_wrapper as _write_wrapper,
)

VARIANT_METADATA = "variant.json"

_THEME_PROMPT_TWEAKS = ("themes", "prompt-overlays")
_NATIVE_REGEX_TWEAKS = ("hide-startup-banner", "hide-startup-clawd")
_IN_PLACE_TWEAKS = (*_THEME_PROMPT_TWEAKS, *_NATIVE_REGEX_TWEAKS, *ENV_TWEAK_IDS)


class _BuildStageRecorder:
    def __init__(self, variant_id: str):
        self.variant_id = variant_id
        self.stages: List[VariantBuildStage] = []

    def run(self, name: str, func, *, detail: str = ""):
        stage = VariantBuildStage(name=name, status="running", detail=detail)
        self.stages.append(stage)
        try:
            result = func()
        except VariantBuildError:
            raise
        except Exception as exc:
            stage.status = "failed"
            stage.detail = _join_stage_detail(detail, str(exc))
            raise VariantBuildError(self.variant_id, name, exc, self.stages) from exc
        stage.status = "ok"
        return result


def _join_stage_detail(prefix: str, suffix: str) -> str:
    if prefix and suffix:
        return f"{prefix}: {suffix}"
    return prefix or suffix


def _resolve_bin_dir(bin_dir, root) -> Path:
    if bin_dir is None:
        return default_bin_dir(root)
    return Path(bin_dir)


def _canonical_wrapper_path(variant_id: str, root=None) -> Path:
    return default_bin_dir(root) / variant_id


def _classify_theme_prompt_tweaks(tweak_ids, *, theme_done: bool, prompt_done: bool):
    applied: List[str] = []
    skipped: List[str] = []
    if "themes" in tweak_ids:
        (applied if theme_done else skipped).append("themes")
    if "prompt-overlays" in tweak_ids:
        (applied if prompt_done else skipped).append("prompt-overlays")
    return applied, skipped


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
    mcp_ids: Optional[Iterable[str]] = None,
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
    selected_mcp_ids = normalize_mcp_ids(mcp_ids or [])
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
        "mcp": {
            "selected": selected_mcp_ids,
        },
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
        bin_dir=_resolve_bin_dir(bin_dir, root),
        source_artifact=source_artifact,
    )


def apply_variant(variant_id: str, *, claude_version: Optional[str] = None, root=None) -> VariantBuildResult:
    variant = load_variant(variant_id, root=root)
    return _apply_variant_manifest(variant.manifest, claude_version=claude_version, root=root)


def _apply_variant_manifest(manifest: Dict, *, claude_version: Optional[str] = None, root=None) -> VariantBuildResult:
    manifest = dict(manifest)
    if claude_version:
        manifest["source"] = dict(manifest["source"])
        manifest["source"]["version"] = claude_version
    manifest["updatedAt"] = _utc_now()
    return _build_variant_from_manifest(
        manifest,
        root=root,
        bin_dir=default_bin_dir(root),
    )


def update_variants(
    name: Optional[str] = None,
    *,
    all_variants: bool = False,
    claude_version: Optional[str] = None,
    root=None,
) -> List[VariantBuildResult]:
    if all_variants:
        return [
            _apply_variant_manifest(variant.manifest, claude_version=claude_version, root=root)
            for variant in scan_variants(root)
        ]
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
    wrapper_path = _canonical_wrapper_path(variant_id, root=root)
    if wrapper_path.exists():
        wrapper_path.unlink()
    shutil.rmtree(variant.path)
    return True


def doctor_variant(name: Optional[str] = None, *, all_variants: bool = False, root=None) -> List[Dict[str, object]]:
    if all_variants or not name:
        variants = scan_variants(root)
    else:
        variants = [load_variant(variant_id_from_name(name), root=root)]
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
        credential = variant.manifest.get("credential", {})
        if credential.get("mode") == "stored":
            secrets_path = Path(credential.get("secretsPath") or secrets_path)
            checks.append({"name": "secrets", "ok": secrets_path.is_file() and not secrets_path.is_symlink(), "path": str(secrets_path)})
            if secrets_path.exists() and not secrets_path.is_symlink() and os.name != "nt":
                mode_ok = (secrets_path.stat().st_mode & 0o777) == SECRETS_FILE_MODE
                checks.append({"name": "secrets-mode", "ok": mode_ok, "path": str(secrets_path)})
            if secrets_path.exists():
                try:
                    _validate_secret_file(secrets_path)
                    secret_safe = True
                    secret_detail = ""
                except ValueError as exc:
                    secret_safe = False
                    secret_detail = str(exc)
                checks.append({"name": "secrets-safe", "ok": secret_safe, "path": str(secrets_path), "detail": secret_detail})
        ok = all(check["ok"] for check in checks)
        reports.append({"id": variant.variant_id, "name": variant.name, "ok": ok, "checks": checks})
    return reports


def run_variant(name: str, args: Optional[List[str]] = None, root=None) -> int:
    variant_id = variant_id_from_name(name)
    load_variant(variant_id, root=root)
    wrapper = _canonical_wrapper_path(variant_id, root=root)
    if not wrapper.exists():
        raise ValueError(f"Variant wrapper is missing: {wrapper}")
    try:
        result = subprocess.run([str(wrapper), *(args or [])], check=False, timeout=300)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Variant '{name}' timed out after 300s") from exc
    return result.returncode


# -- internal builders -------------------------------------------------------

def _build_variant_from_manifest(
    manifest: Dict,
    *,
    root=None,
    bin_dir: Path,
    source_artifact: Optional[NativeArtifact] = None,
) -> VariantBuildResult:
    variant_id = manifest["id"]
    stages = _BuildStageRecorder(variant_id)
    variant_dir = variant_root(variant_id, root=root)
    native_dir = variant_dir / "native"
    unpacked_dir = variant_dir / "unpacked"
    config_dir = variant_dir / "config"
    tweakcc_dir = variant_dir / "tweakcc"
    tmp_dir = variant_dir / "tmp"
    def prepare_dirs():
        for path in (native_dir, config_dir, tweakcc_dir, tmp_dir, bin_dir):
            path.mkdir(parents=True, exist_ok=True)

    stages.run("prepare directories", prepare_dirs, detail=str(variant_dir))

    if source_artifact is None:
        source_artifact = stages.run(
            "download source",
            lambda: _download_source_artifact(manifest["source"]["version"], root=root),
            detail=str(manifest["source"]["version"]),
        )
    binary_name = native_binary_filename(source_artifact.platform)
    output_binary = native_dir / binary_name
    runtime = "native"
    entry_path = None

    if _can_use_in_place_variant_patch(source_artifact, manifest):
        runtime_result = stages.run(
            "patch binary",
            lambda: _copy_patch_or_unpack_variant_binary(
                source_artifact,
                output_binary,
                unpacked_dir,
                provider_key=manifest["provider"]["key"],
                tweak_ids=manifest.get("tweaks", []),
            ),
            detail=str(output_binary),
        )
        tweak_result = runtime_result.tweaks
        sign_result = runtime_result.sign_result
        runtime = runtime_result.runtime
        entry_path = runtime_result.entry_path
    elif _should_use_unpacked_node_runtime(source_artifact, manifest):
        runtime_result = stages.run(
            "unpack node runtime",
            lambda: _copy_unpack_node_runtime_variant(
                source_artifact,
                output_binary,
                unpacked_dir,
                provider_key=manifest["provider"]["key"],
                tweak_ids=manifest.get("tweaks", []),
            ),
            detail=str(unpacked_dir),
        )
        tweak_result = runtime_result.tweaks
        sign_result = runtime_result.sign_result
        runtime = runtime_result.runtime
        entry_path = runtime_result.entry_path
    else:
        def rebuild_from_extract():
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
                local_tweak_result = _patch_entry_js(
                    extract_dir,
                    manifest_data,
                    provider_key=manifest["provider"]["key"],
                    tweak_ids=manifest.get("tweaks", []),
                    claude_version=source_artifact.version,
                )
                pack_bundle(str(extract_dir), str(staged_output), str(source_artifact.path))
                shutil.move(str(staged_output), str(output_binary))
                if os.name != "nt":
                    os.chmod(output_binary, 0o755)
                return local_tweak_result, try_adhoc_sign(str(output_binary))

        tweak_result, sign_result = stages.run(
            "extract patch repack",
            rebuild_from_extract,
            detail=str(output_binary),
        )

    output_sha256 = stages.run("hash output", lambda: file_sha256(output_binary), detail=str(output_binary))
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
    stages.run("write runtime config", lambda: _write_variant_config(manifest), detail=str(config_dir))
    wrapper_path = stages.run("write command", lambda: _write_wrapper(manifest), detail=str(bin_dir / variant_id))
    manifest["paths"]["wrapper"] = str(wrapper_path)
    manifest["updatedAt"] = _utc_now()
    stages.run("write setup config", lambda: write_json(variant_dir / VARIANT_METADATA, manifest), detail=str(variant_dir / VARIANT_METADATA))
    variant = stages.run("load setup", lambda: load_variant(variant_id, root=root), detail=str(variant_dir / VARIANT_METADATA))
    return VariantBuildResult(
        variant=variant,
        binary_path=output_binary,
        wrapper_path=wrapper_path,
        output_sha256=output_sha256,
        applied_tweaks=tweak_result.applied,
        skipped_tweaks=tweak_result.skipped,
        missing_prompt_keys=tweak_result.missing,
        stages=stages.stages,
    )


def _download_source_artifact(version: str, root=None) -> NativeArtifact:
    requested = _resolve_source_version(version, root=root)
    with _workspace_env(root):
        path = download_binary(requested)
    artifact = native_artifact_from_path(path, root=root)
    if artifact is None:
        raise ValueError(f"Downloaded binary was not found in workspace: {path}")
    return artifact


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
    native_regex_tweaks = [tweak_id for tweak_id in tweak_ids if tweak_id in _NATIVE_REGEX_TWEAKS]
    provider = get_provider(provider_key)
    result = apply_patches(
        PatchInputs(
            binary_path=str(output_binary),
            config=config,
            overlays=overlays,
            regex_tweaks=native_regex_tweaks,
            provider_label=provider.label,
            claude_version=source_artifact.version,
        )
    )
    if result.ok and result.skipped_reason == "macho-grow-not-supported" and (config or overlays or native_regex_tweaks):
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

    missing = list(getattr(result, "missing_prompt_keys", []) or [])
    if result.skipped_reason:
        applied, skipped = _classify_theme_prompt_tweaks(tweak_ids, theme_done=False, prompt_done=False)
    else:
        applied, skipped = _classify_theme_prompt_tweaks(
            tweak_ids,
            theme_done=bool(config),
            prompt_done=bool(overlays),
        )
        applied.extend(getattr(result, "curated_applied", []) or [])
        skipped.extend(getattr(result, "curated_skipped", []) or [])
    skipped.extend(
        tweak_id for tweak_id in tweak_ids
        if tweak_id not in _THEME_PROMPT_TWEAKS
        and tweak_id not in _NATIVE_REGEX_TWEAKS
        and tweak_id not in skipped
    )
    sign_result = try_adhoc_sign(str(output_binary)) if not result.resigned else _AlreadySigned()
    return _RuntimePatchResult(
        tweaks=_BinaryTweakResult(applied, skipped, missing),
        sign_result=sign_result,
    )


def _should_use_unpacked_node_runtime(source_artifact: NativeArtifact, manifest: Dict) -> bool:
    tweak_ids = set(manifest.get("tweaks") or [])
    return (
        source_artifact.platform.startswith("darwin")
        and not manifest.get("patches")
        and not tweak_ids.issubset(_IN_PLACE_TWEAKS)
    )


def _copy_unpack_node_runtime_variant(
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
    return _unpack_node_runtime_variant(
        source_artifact,
        output_binary,
        unpacked_dir,
        provider_key=provider_key,
        tweak_ids=tweak_ids,
        config=config,
        overlays=overlays,
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
        managed_root=str(unpacked_dir.parent),
        config=config,
        overlays=overlays,
    )
    missing = list(result.patch.prompt_missing or [])
    applied, skipped = _classify_theme_prompt_tweaks(
        tweak_ids,
        theme_done=bool(result.patch.theme_replaced),
        prompt_done=bool(result.patch.prompt_replaced),
    )

    remaining_tweaks = [tweak_id for tweak_id in tweak_ids if tweak_id not in _THEME_PROMPT_TWEAKS]
    if remaining_tweaks:
        entry_path = Path(result.entry_path)
        js = entry_path.read_text(encoding="latin1")
        extra = apply_variant_tweaks(
            js,
            tweak_ids=remaining_tweaks,
            config={},
            overlays={},
            provider_label=provider.label,
            claude_version=source_artifact.version,
        )
        atomic_write_text_no_symlink(entry_path, extra.js, encoding="latin1")
        applied.extend(extra.applied)
        skipped.extend(extra.skipped)
        missing.extend(extra.missing)

    return _RuntimePatchResult(
        tweaks=_BinaryTweakResult(applied, skipped, missing),
        sign_result=_AlreadySigned(),
        runtime="node",
        entry_path=result.entry_path,
    )


__all__ = [
    "DEFAULT_TWEAK_IDS",
    "SECRETS_FILE",
    "VARIANT_METADATA",
    "Variant",
    "VariantBuildError",
    "VariantBuildResult",
    "VariantBuildStage",
    "apply_variant",
    "apply_variant_tweaks",
    "create_variant",
    "default_bin_dir",
    "doctor_variant",
    "env_for_tweaks",
    "list_variant_providers",
    "load_variant",
    "normalize_tweak_ids",
    "normalize_mcp_ids",
    "remove_variant",
    "run_variant",
    "scan_variants",
    "update_variants",
    "validate_variant_manifest",
    "variant_id_from_name",
    "variant_root",
]
