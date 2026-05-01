"""Curated entry-JS tweaks applied to Claude Code variants."""

import json
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from ..binary_patcher.prompts import apply_prompts
from ..binary_patcher.theme import apply_theme, themes_from_config as _themes_from_config
from ..patches import PatchContext as _PatchCtx, apply_patches as _apply_patches, PatchAnchorMissError
from ..patches._registry import REGISTRY as _PATCH_REGISTRY


DEFAULT_TWEAK_IDS = ["themes", "prompt-overlays", "patches-applied-indication"]
ENV_TWEAK_IDS = ["context-limit", "file-read-limit", "subagent-model"]
CURATED_TWEAK_IDS = [
    "themes",
    "prompt-overlays",
    "show-more-items-in-select-menus",
    "model-customizations",
    "hide-startup-banner",
    "hide-startup-clawd",
    "hide-ctrl-g-to-edit",
    "suppress-line-numbers",
    "auto-accept-plan-mode",
    "allow-custom-agent-models",
    "patches-applied-indication",
    *ENV_TWEAK_IDS,
]


CUSTOM_MODELS = [
    {"value": "claude-opus-4-6", "label": "Opus 4.6", "description": "Claude Opus 4.6"},
    {"value": "claude-sonnet-4-6", "label": "Sonnet 4.6", "description": "Claude Sonnet 4.6"},
    {"value": "claude-haiku-4-5-20251001", "label": "Haiku 4.5", "description": "Claude Haiku 4.5"},
    {"value": "claude-opus-4-5-20251101", "label": "Opus 4.5", "description": "Claude Opus 4.5"},
    {"value": "claude-sonnet-4-5-20250929", "label": "Sonnet 4.5", "description": "Claude Sonnet 4.5"},
    {"value": "claude-opus-4-20250514", "label": "Opus 4", "description": "Claude Opus 4"},
    {"value": "claude-sonnet-4-20250514", "label": "Sonnet 4", "description": "Claude Sonnet 4"},
    {"value": "claude-3-7-sonnet-20250219", "label": "Sonnet 3.7", "description": "Claude 3.7 Sonnet"},
    {"value": "claude-3-5-haiku-20241022", "label": "Haiku 3.5", "description": "Claude 3.5 Haiku"},
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
        {"id": tweak_id, "envBacked": tweak_id in ENV_TWEAK_IDS}
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
    return env


def apply_variant_tweaks(
    js: str,
    *,
    tweak_ids: Iterable[str],
    config: Optional[Dict] = None,
    overlays: Optional[Dict[str, str]] = None,
    provider_label: str = "cc-extractor",
) -> TweakResult:
    config = config or {}
    overlays = overlays or {}
    applied: List[str] = []
    skipped: List[str] = []
    missing: List[str] = []

    for tweak_id in normalize_tweak_ids(tweak_ids):
        if tweak_id in ENV_TWEAK_IDS:
            skipped.append(tweak_id)
            continue
        old_js = js
        if tweak_id == "themes":
            themed = apply_theme(js, _themes_from_config(config))
            js = themed.js
            if themed.replaced:
                applied.append(tweak_id)
            else:
                skipped.append(tweak_id)
        elif tweak_id == "prompt-overlays":
            prompt_result = apply_prompts(js, overlays)
            js = prompt_result.js
            missing.extend(prompt_result.missing)
            if prompt_result.replaced_targets:
                applied.append(tweak_id)
            else:
                skipped.append(tweak_id)
        elif tweak_id in _PATCH_REGISTRY:
            try:
                sub = _apply_patches(
                    js,
                    [tweak_id],
                    _PatchCtx(
                        claude_version=None,
                        provider_label=provider_label,
                        config=config,
                        overlays=overlays,
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
        else:
            patcher = _PATCHERS[tweak_id]
            patched = patcher(js, provider_label=provider_label)
            if patched is None:
                raise TweakPatchError(tweak_id, "failed to find anchor")
            js = patched
            if js != old_js:
                applied.append(tweak_id)
            else:
                skipped.append(tweak_id)

    return TweakResult(js=js, applied=applied, skipped=skipped, missing=missing)


def _show_more_items(js: str, **kwargs) -> Optional[str]:
    matches = list(re.finditer(r"visibleOptionCount:[$\w]+=(\d+)", js))
    if not matches:
        return None
    for match in reversed(matches):
        start = match.start(1)
        js = js[:start] + "25" + js[match.end(1):]
    height = re.search(r"(\{rows:([$\w]+),columns:[$\w]+\}=[$\w]+\(\),)([$\w]+)=Math\.floor\(\2/2\)", js)
    if height:
        js = js[:height.start()] + f"{height.group(1)}{height.group(3)}={height.group(2)}" + js[height.end():]
    replacements = [
        (r"Math\.max\(1,Math\.floor\(\(([$\w]+)-10\)/2\)\)", r"Math.max(1,\1-3)"),
        (r"Math\.min\(6,Math\.max\(1,([$\w]+)-3\)\)", r"Math.max(1,\1-3)"),
    ]
    for pattern, repl in replacements:
        js = re.sub(pattern, repl, js, count=1)
    return js


def _model_customizations(js: str, **kwargs) -> Optional[str]:
    match = re.search(r" ([$\w]+)\.push\(\{value:[$\w]+,label:[$\w]+,description:\"Custom model\"\}\)", js)
    if not match:
        return None
    model_var = match.group(1)
    search_start = max(0, match.start() - 1500)
    chunk = js[search_start:match.start()]
    func_pattern = re.compile(rf"function [$\w]+\([^)]*\)\{{(?:let|var|const) {re.escape(model_var)}=.+?;")
    last = None
    for found in func_pattern.finditer(chunk):
        last = found
    if last is None:
        return None
    insertion_index = search_start + last.end()
    inject = "".join(f"{model_var}.push({json.dumps(model, separators=(',', ':'))});" for model in CUSTOM_MODELS)
    return js[:insertion_index] + inject + js[insertion_index:]


def _hide_startup_banner(js: str, **kwargs) -> Optional[str]:
    match = re.search(r",[$\w]+\.createElement\([$\w]+,\{isBeforeFirstMessage:!1\}\),", js)
    if match:
        return js[:match.start()] + "," + js[match.end():]

    for match in re.finditer(r"(function ([$\w]+)\(\)\{)(?=[^}]{0,500}Apple_Terminal)", js):
        body_start = match.end()
        if "Welcome to Claude Code" in js[body_start:body_start + 5000]:
            return js[:body_start] + "return null;" + js[body_start:]
    return None


def _hide_startup_clawd(js: str, **kwargs) -> Optional[str]:
    match = re.search(r"▛███▜|\\u259B\\u2588\\u2588\\u2588\\u259C", js, re.IGNORECASE)
    if not match:
        return None
    lookback_start = max(0, match.start() - 2000)
    before = js[lookback_start:match.start()]
    funcs = list(re.finditer(r"function ([$\w]+)\([^)]*\)\{", before))
    if not funcs:
        return None
    inner_name = funcs[-1].group(1)
    for wrapper in re.finditer(r"function ([$\w]+)\([^)]*\)\{", js):
        body_start = wrapper.end()
        body = js[body_start:body_start + 500]
        elem_idx = body.find(f"createElement({inner_name},")
        if elem_idx == -1:
            continue
        next_func_idx = body.find("function ")
        if next_func_idx != -1 and next_func_idx < elem_idx:
            continue
        return js[:body_start] + "return null;" + js[body_start:]
    inner_start = lookback_start + funcs[-1].end()
    return js[:inner_start] + "return null;" + js[inner_start:]


def _hide_ctrl_g_to_edit(js: str, **kwargs) -> Optional[str]:
    match = re.search(r"if\(([$\w]+&&[$\w]+)\)[$\w]+\(\"tengu_external_editor_hint_shown\",", js)
    if not match:
        return None
    return js[:match.start(1)] + "false" + js[match.end(1):]


def _suppress_line_numbers(js: str, **kwargs) -> Optional[str]:
    sig = re.search(r"\{content:([$\w]+),startLine:[$\w]+\}\)\{if\(!\1\)return\"\";let ([$\w]+)=\1\.split\([^)]+\);", js)
    if sig:
        replace_start = sig.end()
        end = re.search(r"\}(?=function |var |let |const |[$\w]+=[$\w]+\()", js[replace_start:])
        if end:
            return js[:replace_start] + f"return {sig.group(1)}" + js[replace_start + end.start():]

    arrow = re.search(
        r"if\(([$\w]+)\.length>=\d+\)return`\$\{\1\}(?:→|\\u2192)\$\{([$\w]+)\}`;return`\$\{\1\.padStart\(\d+,\" \"\)\}(?:→|\\u2192)\$\{\2\}`",
        js,
    )
    if arrow:
        return js[:arrow.start()] + f"return {arrow.group(2)}" + js[arrow.end():]
    return None


def _auto_accept_plan_mode(js: str, **kwargs) -> Optional[str]:
    ready_idx = js.find('title:"Ready to code?"')
    if ready_idx == -1:
        return None
    if re.search(r"[$\w]+(?:\.current)?\(\"yes-accept-edits\"\);return null;return", js):
        return js
    after = js[ready_idx:ready_idx + 3000]
    accept_func = None
    for pattern in (
        r"onChange:\([$\w]+\)=>([$\w]+)\([$\w]+\),onCancel",
        r"onChange:([$\w]+),onCancel",
        r"onChange:\([$\w]+\)=>void ([$\w]+)\.current\([$\w]+\),onCancel",
    ):
        match = re.search(pattern, after)
        if match:
            accept_func = match.group(1)
            if ".current" not in accept_func and "current" in pattern:
                accept_func += ".current"
            break
    if not accept_func:
        return None
    before_start = max(0, ready_idx - 500)
    before = js[before_start:ready_idx]
    return_idx = before.rfind("return ")
    if return_idx == -1:
        return None
    insert_at = before_start + return_idx
    insertion = f'{accept_func}("yes-accept-edits");return null;'
    return js[:insert_at] + insertion + js[insert_at:]


def _allow_custom_agent_models(js: str, **kwargs) -> Optional[str]:
    zod = re.search(r",model:([$\w]+)\.enum\(([$\w]+)\)\.optional\(\)", js)
    if not zod:
        loose = re.sub(
            r"(let\s+[$\w]+\s*=\s*([$\w]+)\s*&&\s*typeof\s+\2\s*===\"string\")\s*&&\s*[$\w]+\.includes\(\2\)",
            r"\1",
            js,
            count=1,
        )
        return loose if loose != js else js
    zod_var = zod.group(1)
    model_list_var = zod.group(2)
    js = js[:zod.start()] + f",model:{zod_var}.string().optional()" + js[zod.end():]
    pattern = re.compile(
        rf"([;)}}])let\s+([$\w]+)\s*=\s*([$\w]+)\s*&&\s*typeof\s+\3\s*===\"string\"\s*&&\s*{re.escape(model_list_var)}\.includes\(\3\)"
    )
    valid = pattern.search(js)
    if not valid:
        return None
    replacement = f'{valid.group(1)}let {valid.group(2)}={valid.group(3)}&&typeof {valid.group(3)}==="string"'
    return js[:valid.start()] + replacement + js[valid.end():]


def _patches_applied_indication(js: str, provider_label: str = "cc-extractor", **kwargs) -> Optional[str]:
    marker = " (Claude Code)"
    idx = js.find(marker)
    if idx == -1:
        return None
    replacement = f" (Claude Code, {provider_label} variant)"
    return js[:idx] + replacement + js[idx + len(marker):]


_PATCHERS = {
    "auto-accept-plan-mode": _auto_accept_plan_mode,
    "allow-custom-agent-models": _allow_custom_agent_models,
    "patches-applied-indication": _patches_applied_indication,
}
