from dataclasses import dataclass

from .constants import BUNFS_PATH_PREFIXES
from .types import ModuleNotFound, SizeMismatch


@dataclass
class ReplaceResult:
    buf: bytes
    signature_invalidated: bool = False

    @property
    def data(self):
        return self.buf


def replace_module(data, info, module_name, replacement):
    target_name = _normalize_module_name(module_name)
    target = next((module for module in info.modules if module.name == target_name), None)
    if target is None:
        raise ModuleNotFound(f"Module not found in Bun binary: {module_name}")

    replacement = bytes(replacement)
    if len(replacement) != target.cont_len:
        raise SizeMismatch(
            f'replace_module requires same-size content for "{module_name}". '
            f"Expected {target.cont_len} bytes, got {len(replacement)}."
        )

    out = bytearray(data)
    start = info.data_start + target.cont_off
    out[start : start + target.cont_len] = replacement
    return ReplaceResult(
        buf=bytes(out),
        signature_invalidated=info.platform == "macho" and info.has_code_signature,
    )


def _normalize_module_name(name):
    normalized = str(name).replace("\\", "/").lstrip("/")
    for prefix in BUNFS_PATH_PREFIXES:
        stripped_prefix = prefix.lstrip("/")
        if normalized.startswith(stripped_prefix):
            return normalized[len(stripped_prefix) :]
    return normalized
