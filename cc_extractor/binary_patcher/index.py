import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cc_extractor.bun_extract import parse_bun_binary, replace_module
from cc_extractor.bun_extract.types import BunFormatError

from .codesign import try_adhoc_sign
from .pe_resize import PeNotLastSectionError
from .prompts import apply_prompts
from .replace_entry import replace_entry_js
from .theme import ThemeAnchorNotFound, apply_theme


@dataclass
class PatchInputs:
    binary_path: str
    config: dict
    overlays: dict = None


@dataclass
class PatchSuccess:
    ok: Literal[True]
    bytes_changed: int
    resigned: bool
    missing_prompt_keys: list
    codesign_skipped: bool
    skipped_reason: str = None


@dataclass
class PatchFailure:
    ok: Literal[False]
    reason: Literal["anchor-not-found", "resize-bound-exceeded", "io-error"]
    detail: str


def apply_patches(inputs):
    if isinstance(inputs, dict):
        inputs = PatchInputs(**inputs)

    binary_path = Path(inputs.binary_path)
    try:
        data = binary_path.read_bytes()
    except OSError as exc:
        return PatchFailure(ok=False, reason="io-error", detail=f"read {binary_path}: {exc}")

    try:
        info = parse_bun_binary(data)
    except Exception as exc:
        return PatchFailure(ok=False, reason="io-error", detail=f"parse {binary_path}: {exc}")

    if info.entry_point_id < 0 or info.entry_point_id >= len(info.modules):
        return PatchFailure(ok=False, reason="io-error", detail=f"entry module id {info.entry_point_id} out of range")

    entry = info.modules[info.entry_point_id]
    old_entry_len = entry.cont_len
    old_js = data[info.data_start + entry.cont_off : info.data_start + entry.cont_off + old_entry_len].decode("utf-8")

    try:
        theme_result = apply_theme(old_js, _themes_from_config(inputs.config))
        new_js = theme_result.js
    except ThemeAnchorNotFound as exc:
        return PatchFailure(ok=False, reason="anchor-not-found", detail=str(exc))
    except Exception as exc:
        return PatchFailure(ok=False, reason="io-error", detail=f"apply_theme: {exc}")

    missing_prompt_keys = []
    if inputs.overlays:
        prompt_result = apply_prompts(new_js, inputs.overlays)
        new_js = prompt_result.js
        missing_prompt_keys = prompt_result.missing

    bytes_changed = 0
    write_data = None
    skipped_reason = None
    new_content = new_js.encode("utf-8")

    if info.platform == "macho":
        delta = len(new_content) - old_entry_len
        if delta > 0:
            skipped_reason = "macho-grow-not-supported"
        else:
            if delta < 0:
                new_content += b" " * (-delta)
            try:
                write_data = replace_module(data, info, entry.name, new_content).buf
            except Exception as exc:
                return PatchFailure(ok=False, reason="io-error", detail=f"replace_module: {exc}")
    else:
        try:
            result = replace_entry_js(data, info, new_content)
            write_data = result.buf
            bytes_changed = result.delta
        except PeNotLastSectionError as exc:
            return PatchFailure(ok=False, reason="resize-bound-exceeded", detail=str(exc))
        except BunFormatError as exc:
            return PatchFailure(ok=False, reason="io-error", detail=str(exc))
        except Exception as exc:
            return PatchFailure(ok=False, reason="io-error", detail=f"replace_entry_js: {exc}")

    resigned = False
    codesign_skipped = False
    if write_data is not None:
        try:
            binary_path.write_bytes(write_data)
            if os.name != "nt":
                os.chmod(binary_path, 0o755)
        except OSError as exc:
            return PatchFailure(ok=False, reason="io-error", detail=f"write {binary_path}: {exc}")

        if info.platform == "macho" and info.has_code_signature:
            sign_result = try_adhoc_sign(str(binary_path))
            if sign_result.signed:
                resigned = True
            else:
                codesign_skipped = True

    return PatchSuccess(
        ok=True,
        bytes_changed=bytes_changed,
        resigned=resigned,
        missing_prompt_keys=missing_prompt_keys,
        codesign_skipped=codesign_skipped,
        skipped_reason=skipped_reason,
    )


def _themes_from_config(config):
    if config is None:
        return []
    if "settings" in config and isinstance(config["settings"], dict):
        return config["settings"].get("themes") or []
    return config.get("themes") or []
