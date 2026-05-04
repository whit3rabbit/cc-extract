"""Dataclasses and small helpers for the variants subsystem (no I/O)."""

from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Dict, List, Optional

from .._utils import make_kebab_id, require_env_name
from ..workspace import PATCH_ID_RE, workspace_root


@dataclass
class Variant:
    variant_id: str
    name: str
    path: Path
    manifest: Dict


@dataclass
class VariantBuildStage:
    name: str
    status: str
    detail: str = ""


class VariantBuildError(RuntimeError):
    def __init__(self, variant_id: str, stage: str, cause: Exception, stages: List[VariantBuildStage]):
        self.variant_id = variant_id
        self.stage = stage
        self.cause = cause
        self.stages = list(stages)
        super().__init__(f"{stage} failed for {variant_id}: {cause}")


@dataclass
class VariantBuildResult:
    variant: Variant
    binary_path: Path
    wrapper_path: Path
    output_sha256: str
    applied_tweaks: List[str]
    skipped_tweaks: List[str]
    missing_prompt_keys: List[str]
    stages: List[VariantBuildStage] = dataclass_field(default_factory=list)


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
    reason: Optional[str] = None
    detail: Optional[str] = None


def variant_id_from_name(name: str) -> str:
    return make_kebab_id(name, label="variant name")


def variant_root(variant_id: str, root=None) -> Path:
    if not isinstance(variant_id, str) or not PATCH_ID_RE.match(variant_id):
        raise ValueError("variant id must be lower-kebab-case")
    return workspace_root(root) / "variants" / variant_id


def default_bin_dir(root=None) -> Path:
    return workspace_root(root) / "bin"


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
    mcp = manifest.get("mcp", {})
    if mcp is None:
        mcp = {}
    if not isinstance(mcp, dict):
        raise ValueError("variant mcp must be an object")
    selected_mcp = mcp.get("selected", [])
    if selected_mcp is None:
        selected_mcp = []
    if not isinstance(selected_mcp, list) or not all(isinstance(item, str) for item in selected_mcp):
        raise ValueError("variant mcp.selected must be a list of strings")
    if selected_mcp:
        from ..providers import normalize_mcp_ids

        normalize_mcp_ids(selected_mcp)
    env_unset = manifest.get("envUnset", [])
    if env_unset is None:
        env_unset = []
    if not isinstance(env_unset, list):
        raise ValueError("variant envUnset must be a list of strings")
    for name in env_unset:
        if not isinstance(name, str):
            raise ValueError("variant envUnset must be a list of strings")
        require_env_name(name, label="variant envUnset item")
    for field in ("createdAt", "updatedAt"):
        if not isinstance(manifest.get(field), str) or not manifest[field]:
            raise ValueError(f"variant {field} must be a non-empty string")


def list_variant_providers() -> List[Dict[str, object]]:
    from ..providers import list_providers

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
                "envUnset": list(provider.env_unset),
                "mcpServers": sorted(provider.mcp_servers),
                "settingsPermissionsDeny": list(provider.settings_permissions_deny),
                "tui": dict(provider.tui),
                "defaultVariantName": provider.default_variant_name or provider.key,
            }
        )
    return providers
