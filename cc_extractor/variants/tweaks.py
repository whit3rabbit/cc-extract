"""Registry-delegating shim for variant tweaks. All tweaks are registered in patches._registry."""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from ..patches import PatchContext as _PatchCtx, apply_patches as _apply_patches, PatchAnchorMissError
from ..patches._registry import REGISTRY as _PATCH_REGISTRY
from ..patches.model_customizations import CUSTOM_MODELS  # noqa: F401 (legacy re-export)


DEFAULT_TWEAK_IDS = [
    "themes",
    "prompt-overlays",
    "hide-startup-banner",
    "hide-startup-clawd",
    "mcp-non-blocking",
    "mcp-batch-size",
    "rtk-shell-prefix",
]
ENV_TWEAK_IDS = ["context-limit", "file-read-limit", "subagent-model"]
PROMPT_ONLY_TWEAK_IDS = ["rtk-shell-prefix"]
SETUP_ENV_ONLY_TWEAK_IDS = ["mcp-batch-size"]
CURATED_TWEAK_IDS = [
    "themes",
    "prompt-overlays",
    "show-more-items-in-select-menus",
    "model-customizations",
    "hide-startup-banner",
    "hide-startup-clawd",
    "hide-ctrl-g-to-edit",
    "suppress-line-numbers",
    "suppress-native-installer-warning",
    "suppress-rate-limit-options",
    "thinking-visibility",
    "input-box-border",
    "filter-scroll-escape-sequences",
    "agents-md",
    "session-memory",
    "remember-skill",
    "opusplan1m",
    "mcp-non-blocking",
    "mcp-batch-size",
    "rtk-shell-prefix",
    "token-count-rounding",
    "statusline-update-throttle",
    "auto-accept-plan-mode",
    "allow-custom-agent-models",
    "patches-applied-indication",
    *ENV_TWEAK_IDS,
]
DASHBOARD_EXCLUDED_TWEAK_IDS = {
    "themes",
    "prompt-overlays",
    "remember-skill",
    "rtk-shell-prefix",
    *ENV_TWEAK_IDS,
}
DASHBOARD_TWEAK_IDS = [
    tweak_id for tweak_id in CURATED_TWEAK_IDS
    if tweak_id not in DASHBOARD_EXCLUDED_TWEAK_IDS
]


@dataclass
class TweakResult:
    js: str
    applied: List[str]
    skipped: List[str]
    missing: List[str]


class TweakPatchError(ValueError):
    def __init__(self, tweak_id: str, detail: str):
        self.tweak_id = tweak_id
        self.detail = detail
        super().__init__(f"{tweak_id}: {detail}")


RTK_SHELL_PREFIX_TEXT = (
    "When running shell commands through Bash, prefix each command with `rtk` "
    "unless the user explicitly asks otherwise or `rtk` is unavailable."
)
RTK_PROMPT_TARGETS = ("explore", "planEnhanced")
MCP_BATCH_SIZE_ENV = "MCP_SERVER_CONNECTION_BATCH_SIZE"
MCP_BATCH_SIZE_DEFAULT = "10"
MANAGED_TWEAK_ENV_KEYS = (
    "CLAUDE_CODE_CONTEXT_LIMIT",
    "DISABLE_COMPACT",
    "CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS",
    "CLAUDE_CODE_SUBAGENT_MODEL",
    MCP_BATCH_SIZE_ENV,
)


def compose_prompt_overlays(
    base_overlays: Optional[Dict[str, str]],
    tweak_ids: Iterable[str],
) -> Dict[str, str]:
    overlays = dict(base_overlays or {})
    ids = set(tweak_ids)
    if "rtk-shell-prefix" in ids:
        for key in RTK_PROMPT_TARGETS:
            overlays[key] = _append_overlay(overlays.get(key), RTK_SHELL_PREFIX_TEXT)
    return overlays


def _append_overlay(existing: Optional[str], addition: str) -> str:
    existing_text = str(existing or "").strip()
    if not existing_text:
        return addition
    if addition in existing_text:
        return existing_text
    return f"{existing_text}\n\n{addition}"


def normalize_tweak_ids(tweak_ids: Optional[Iterable[str]]) -> List[str]:
    ids = list(tweak_ids or DEFAULT_TWEAK_IDS)
    result = []
    for tweak_id in ids:
        if tweak_id not in CURATED_TWEAK_IDS:
            raise ValueError(f"Unknown tweak: {tweak_id}")
        if tweak_id not in result:
            result.append(tweak_id)
    return result


def available_tweaks() -> List[Dict[str, object]]:
    return [
        {
            "id": tweak_id,
            "envBacked": tweak_id in ENV_TWEAK_IDS,
            "promptOnly": tweak_id in PROMPT_ONLY_TWEAK_IDS,
        }
        for tweak_id in CURATED_TWEAK_IDS
    ]


def env_for_tweaks(tweak_ids: Iterable[str], options: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    options = options or {}
    env = {}
    ids = set(tweak_ids)
    if "context-limit" in ids and options.get("context_limit"):
        env["CLAUDE_CODE_CONTEXT_LIMIT"] = str(options["context_limit"])
        env["DISABLE_COMPACT"] = env.get("DISABLE_COMPACT", "1")
    if "file-read-limit" in ids and options.get("file_read_limit"):
        env["CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS"] = str(options["file_read_limit"])
    if "subagent-model" in ids and options.get("subagent_model"):
        env["CLAUDE_CODE_SUBAGENT_MODEL"] = str(options["subagent_model"])
    if "mcp-batch-size" in ids:
        env[MCP_BATCH_SIZE_ENV] = str(options.get("mcp_batch_size") or MCP_BATCH_SIZE_DEFAULT)
    return env


def sync_tweak_env(
    env: Optional[Dict[str, str]],
    tweak_ids: Iterable[str],
    options: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    synced = dict(env or {})
    for key in MANAGED_TWEAK_ENV_KEYS:
        synced.pop(key, None)
    synced.update(env_for_tweaks(tweak_ids, options))
    return synced


def apply_variant_tweaks(
    js: str,
    *,
    tweak_ids: Iterable[str],
    config: Optional[Dict] = None,
    overlays: Optional[Dict[str, str]] = None,
    provider_label: str = "cc-extractor",
    claude_version: Optional[str] = None,
    force: bool = False,
) -> TweakResult:
    config = config or {}
    overlays = overlays or {}
    applied: List[str] = []
    skipped: List[str] = []
    missing: List[str] = []
    prompt_overlay_done = False

    for tweak_id in normalize_tweak_ids(tweak_ids):
        if tweak_id in ENV_TWEAK_IDS:
            skipped.append(tweak_id)
            continue
        if tweak_id in PROMPT_ONLY_TWEAK_IDS:
            if not overlays:
                skipped.append(tweak_id)
                continue
            if not prompt_overlay_done:
                sub = _apply_patches(
                    js,
                    ["prompt-overlays"],
                    _PatchCtx(
                        claude_version=claude_version,
                        provider_label=provider_label,
                        config=config,
                        overlays=overlays,
                        force=force,
                    ),
                    registry=_PATCH_REGISTRY,
                )
                js = sub.js
                prompt_overlay_done = bool(sub.applied)
                for note in sub.notes:
                    if note.startswith("prompt overlay miss: "):
                        missing.append(note[len("prompt overlay miss: "):])
            (applied if prompt_overlay_done else skipped).append(tweak_id)
            continue
        if tweak_id not in _PATCH_REGISTRY:
            raise TweakPatchError(tweak_id, "unknown tweak (not registered)")
        try:
            sub = _apply_patches(
                js,
                [tweak_id],
                _PatchCtx(
                    claude_version=claude_version,
                    provider_label=provider_label,
                    config=config,
                    overlays=overlays,
                    force=force,
                ),
                registry=_PATCH_REGISTRY,
            )
        except PatchAnchorMissError as e:
            raise TweakPatchError(tweak_id, "failed to find anchor") from e
        js = sub.js
        if sub.applied:
            applied.append(tweak_id)
        else:
            skipped.append(tweak_id)
        if tweak_id == "prompt-overlays":
            prompt_overlay_done = bool(sub.applied)
        # Forward prompt-overlay miss notes to the legacy `missing` list
        for note in sub.notes:
            if note.startswith("prompt overlay miss: "):
                missing.append(note[len("prompt overlay miss: "):])

    return TweakResult(js=js, applied=applied, skipped=skipped, missing=missing)
