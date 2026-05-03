"""Write extracted Bun modules and manifest to disk."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .._utils import safe_child_path, safe_relative_path
from .types import BunFormatError


@dataclass
class ExtractAllResult:
    written: List[str]
    manifest_path: Optional[str] = None
    manifest: Optional[dict] = None


def extract_all(data, info, out_dir, write_sourcemaps=False, manifest=True):
    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    written = []

    manifest_data = _build_manifest(info)

    for module in info.modules:
        rel_path = _sanitize_rel_path(module.name)
        module_info = manifest_data["modules"][module.index]
        module_info["rel_path"] = rel_path

        if module.cont_len > 0:
            out_path = _safe_extract_path(out_root, rel_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(data[info.data_start + module.cont_off : info.data_start + module.cont_off + module.cont_len])
            module_info["sourceFile"] = rel_path
            written.append(str(out_path))

        if write_sourcemaps and module.smap_len > 0:
            smap_rel = rel_path + ".map"
            smap_path = _safe_extract_path(out_root, smap_rel)
            smap_path.parent.mkdir(parents=True, exist_ok=True)
            smap_path.write_bytes(
                data[info.data_start + module.smap_off : info.data_start + module.smap_off + module.smap_len]
            )
            module_info["sourcemapFile"] = smap_rel
            written.append(str(smap_path))

        if module.bc_len > 0:
            bc_rel = rel_path + ".bc"
            bc_path = _safe_extract_path(out_root, bc_rel)
            bc_path.parent.mkdir(parents=True, exist_ok=True)
            bc_path.write_bytes(data[info.data_start + module.bc_off : info.data_start + module.bc_off + module.bc_len])
            module_info["bytecodeFile"] = bc_rel
            written.append(str(bc_path))

    manifest_path = None
    if manifest:
        manifest_path = out_root / ".bundle_manifest.json"
        manifest_path.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")

    return ExtractAllResult(
        written=written,
        manifest_path=str(manifest_path) if manifest_path is not None else None,
        manifest=manifest_data,
    )


def _build_manifest(info):
    entry = info.modules[info.entry_point_id].name if 0 <= info.entry_point_id < len(info.modules) else None
    return {
        "platform": info.platform,
        "isMacho": info.platform == "macho",
        "moduleSize": info.module_size,
        "bunVersionHint": info.bun_version_hint,
        "entryPoint": entry,
        "entryPointId": info.entry_point_id,
        "byteCount": info.byte_count,
        "flags": info.flags,
        "sectionOffset": info.section_offset,
        "sectionSize": info.section_size,
        "hasCodeSignature": info.has_code_signature,
        "execArgvOffset": 0,
        "execArgvLength": 0,
        "modules": [
            {
                "index": module.index,
                "name": module.name,
                "isEntry": module.is_entry,
                "sourceSize": module.cont_len,
                "bytecodeSize": module.bc_len,
                "sourcemapSize": module.smap_len,
                "contentOffset": module.cont_off,
                "sourcemapOffset": module.smap_off,
                "bytecodeOffset": module.bc_off,
                "encoding": module.encoding,
                "loader": module.loader,
                "format": module.format,
                "side": module.side,
            }
            for module in info.modules
        ],
    }


def _sanitize_rel_path(rel_path):
    try:
        return safe_relative_path(rel_path, label="module path")
    except ValueError as exc:
        raise BunFormatError(f"Refusing to extract module with unsafe path: {rel_path}") from exc


def _safe_extract_path(out_root: Path, rel_path: str) -> Path:
    try:
        return safe_child_path(out_root, rel_path, label="module path")
    except ValueError as exc:
        raise BunFormatError(f"Refusing to extract module with unsafe path: {rel_path}") from exc
