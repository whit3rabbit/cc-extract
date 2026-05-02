"""Support AGENTS.md and other CLAUDE.md alternative filenames."""

import json
import re

from . import Patch, PatchContext, PatchOutcome


DEFAULT_ALT_NAMES = [
    "AGENTS.md",
    "GEMINI.md",
    "CRUSH.md",
    "QWEN.md",
    "IFLOW.md",
    "WARP.md",
    "copilot-instructions.md",
]


def _alt_names(ctx: PatchContext):
    settings = (ctx.config or {}).get("settings") or {}
    return settings.get("claudeMdAltNames") or (ctx.config or {}).get("claude_md_alt_names") or DEFAULT_ALT_NAMES


def _apply_async(js: str, alt_names) -> str:
    pattern = re.compile(
        r'(async function ([$\w]+)\(([$\w]+),([$\w]+),([$\w]+))\)\{try\{let ([$\w]+)=await ([$\w]+)\(\)\.readFile\(\3,\{encoding:"utf-8"\}\);'
        r'return ([$\w]+)\(\6,\3,\4,\5\)\}catch\(([$\w]+)\)\{return ([$\w]+)\(\9,\3\),\{info:null,includePaths:\[\]\}\}\}',
        re.DOTALL,
    )
    match = pattern.search(js)
    if not match:
        raise ValueError("async reader")
    func_sig, func_name, path_param, type_param, third_param = match.group(1), match.group(2), match.group(3), match.group(4), match.group(5)
    read_var, fs_getter, processor_func = match.group(6), match.group(7), match.group(8)
    catch_var, error_handler = match.group(9), match.group(10)
    alt_json = json.dumps(alt_names, separators=(",", ":"))
    replacement = (
        f"{func_sig},didReroute){{try{{let {read_var}=await {fs_getter}().readFile({path_param},{{encoding:\"utf-8\"}});"
        f"return {processor_func}({read_var},{path_param},{type_param},{third_param})}}catch({catch_var}){{{error_handler}({catch_var},{path_param});"
        f"if(!didReroute&&({path_param}.endsWith(\"/CLAUDE.md\")||{path_param}.endsWith(\"\\\\CLAUDE.md\"))){{"
        f"for(let alt of {alt_json}){{let altPath={path_param}.slice(0,-9)+alt;"
        f"try{{let r=await {func_name}(altPath,{type_param},{third_param},true);if(r.info)return r}}catch{{}}}}}}"
        f"return{{info:null,includePaths:[]}}}}}}"
    )
    return js[:match.start()] + replacement + js[match.end():]


def _apply_sync(js: str, alt_names) -> str:
    pattern = re.compile(r"(function ([$\w]+)\(([$\w]+),([^)]+?))\)(?:.|\n){0,500}Skipping non-text file in @include")
    match = pattern.search(js)
    if not match:
        raise ValueError("sync reader")
    up_to_params, function_name, first_param, rest_params = match.group(1), match.group(2), match.group(3), match.group(4)
    func_start = match.start()
    fs_match = re.search(r"([$\w]+(?:\(\))?)\.(?:readFileSync|existsSync|statSync)", match.group(0))
    if not fs_match:
        caller = js[max(0, func_start - 5000):func_start]
        fs_match = re.search(r"([$\w]+(?:\(\))?)\.(?:readFileSync|existsSync|statSync)", caller)
    if not fs_match:
        raise ValueError("fs expression")
    fs_expr = fs_match.group(1)
    alt_json = json.dumps(alt_names, separators=(",", ":"))
    sig_index = func_start + len(up_to_params)
    new_js = js[:sig_index] + ",didReroute" + js[sig_index:]
    func_body = new_js[func_start:]
    old_early = re.search(r"\.isFile\(\)\)return null", func_body)
    new_early = re.search(r'==="EISDIR"\)return null', func_body)
    early = old_early or new_early
    if not early:
        raise ValueError("early return")
    fallback = (
        f"if(!didReroute&&({first_param}.endsWith(\"/CLAUDE.md\")||{first_param}.endsWith(\"\\\\CLAUDE.md\"))){{"
        f"for(let alt of {alt_json}){{let altPath={first_param}.slice(0,-9)+alt;"
        f"if({fs_expr}.existsSync(altPath)&&{fs_expr}.statSync(altPath).isFile())return {function_name}(altPath,{rest_params},true);}}}}"
    )
    replacement = f'==="EISDIR"){{{fallback}return null;}}' if new_early else f'.isFile()){{{fallback}return null;}}'
    start = func_start + early.start()
    return new_js[:start] + replacement + new_js[start + len(early.group(0)):]


def _apply(js: str, ctx: PatchContext) -> PatchOutcome:
    alt_names = _alt_names(ctx)
    try:
        return PatchOutcome(js=_apply_async(js, alt_names), status="applied")
    except ValueError:
        try:
            return PatchOutcome(js=_apply_sync(js, alt_names), status="applied")
        except ValueError as exc:
            return PatchOutcome(js=js, status="missed", notes=(f"missing {exc}",))


PATCH = Patch(
    id="agents-md",
    name="AGENTS.md support",
    group="system",
    versions_supported=">=2.1.0,<3",
    versions_tested=(">=2.1.0,<2.2",),
    apply=_apply,
    description="Read AGENTS.md and other configured alternative instruction filenames when CLAUDE.md is absent.",
)
