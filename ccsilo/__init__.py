"""Standalone toolkit for extracting, patching, and repacking Claude Code binaries."""

from importlib import import_module

__all__ = [
    "download_binary",
    "download_npm",
    "extract_all",
    "pack_bundle",
    "apply_patches",
    "parse_bun_binary",
    "replace_entry_js",
    "replace_module",
]

_EXPORTS = {
    "download_binary": ".downloader",
    "download_npm": ".downloader",
    "extract_all": ".extractor",
    "pack_bundle": ".bundler",
    "apply_patches": ".binary_patcher",
    "parse_bun_binary": ".bun_extract",
    "replace_entry_js": ".binary_patcher",
    "replace_module": ".bun_extract",
}


def __getattr__(name):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
