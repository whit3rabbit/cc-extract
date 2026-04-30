"""Per-subcommand handlers invoked by the CLI dispatcher."""

import json
import sys
from pathlib import Path

from ..binary_patcher import PatchInputs, apply_patches, replace_entry_js
from ..bun_extract import parse_bun_binary
from ..bundler import pack_bundle
from ..downloader import download_binary, download_npm, resolve_requested_version
from ..extractor import extract_all
from ..patcher import apply_patch, init_patch
from .payloads import to_jsonable


def inspect_binary(binary_path, as_json=False):
    """Print or return Bun bundle metadata for ``binary_path``."""
    data = Path(binary_path).read_bytes()
    info = parse_bun_binary(data)
    entry = info.modules[info.entry_point_id].name if 0 <= info.entry_point_id < len(info.modules) else None
    payload = {
        "platform": info.platform,
        "moduleSize": info.module_size,
        "moduleCount": len(info.modules),
        "entryPointId": info.entry_point_id,
        "entryPoint": entry,
        "byteCount": info.byte_count,
        "bunVersionHint": info.bun_version_hint,
        "sectionOffset": info.section_offset,
        "sectionSize": info.section_size,
        "hasCodeSignature": info.has_code_signature,
    }

    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"platform: {payload['platform']}")
        print(f"module size: {payload['moduleSize']}")
        print(f"module count: {payload['moduleCount']}")
        print(f"entry point: {payload['entryPoint']}")
        print(f"byte count: {payload['byteCount']}")
        print(f"Bun version hint: {payload['bunVersionHint']}")

    return payload


# -- top-level subcommands ----------------------------------------------------

def cmd_download(args):
    version = resolve_requested_version(args.version, latest=args.latest, npm=args.npm)
    if args.npm:
        download_npm(version, args.outdir)
    else:
        download_binary(version, args.outdir)


def cmd_extract(args):
    extract_all(
        args.binary,
        args.outdir,
        source_version=args.source_version,
        write_sourcemaps=args.include_sourcemaps,
        manifest=args.manifest,
    )


def cmd_unpack(args):
    extract_all(
        args.binary,
        args.out,
        source_version=args.source_version,
        write_sourcemaps=args.include_sourcemaps,
        manifest=args.manifest,
    )


def cmd_inspect(args):
    inspect_binary(args.binary, as_json=args.json)


def cmd_replace_entry(args):
    data = Path(args.binary).read_bytes()
    info = parse_bun_binary(data)
    new_content = Path(args.entry_js).read_bytes()
    result = replace_entry_js(data, info, new_content)
    out_path = Path(args.out)
    out_path.write_bytes(result.buf)
    print(json.dumps(
        {
            "ok": True,
            "delta": result.delta,
            "signatureInvalidated": result.signature_invalidated,
            "signatureStripped": result.signature_stripped,
            "out": str(out_path),
        },
        indent=2,
    ))


def cmd_apply_binary(args):
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    overlays = None
    if args.overlays:
        overlays = json.loads(Path(args.overlays).read_text(encoding="utf-8"))
    result = apply_patches(PatchInputs(binary_path=args.binary, config=config, overlays=overlays))
    print(json.dumps(to_jsonable(result), indent=2))
    if not result.ok:
        sys.exit(1)


def cmd_pack(args):
    pack_bundle(args.indir, args.out_binary, args.base_binary)


def cmd_patch(args, patch_parser):
    if args.patch_command == "init":
        init_patch(args.patch_dir)
    elif args.patch_command == "apply":
        apply_patch(
            args.patch_dir,
            args.extract_dir,
            check=args.check,
            binary_path=args.binary,
            source_version=args.source_version,
        )
    else:
        patch_parser.print_help()
