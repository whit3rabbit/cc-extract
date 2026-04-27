import argparse
import json
import sys
from pathlib import Path

from .bun_extract import parse_bun_binary
from .downloader import download_binary, download_npm, resolve_requested_version
from .extractor import extract_all
from .bundler import pack_bundle
from .patcher import init_patch, apply_patch


def inspect_binary(binary_path, as_json=False):
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


def main():
    parser = argparse.ArgumentParser(description="Bun standalone binary manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Download
    dl_parser = subparsers.add_parser("download", help="Download binary or NPM bundle")
    dl_parser.add_argument("version", nargs="?", help="Version to download")
    dl_parser.add_argument("--latest", action="store_true", help="Download the latest version without prompting")
    dl_parser.add_argument("--npm", action="store_true", help="Download NPM bundle instead of binary")
    dl_parser.add_argument("--outdir", default="downloads", help="Output directory")

    # Extract
    ex_parser = subparsers.add_parser("extract", help="Extract Bun bundle from binary")
    ex_parser.add_argument("binary", help="Path to Bun standalone binary")
    ex_parser.add_argument("outdir", help="Output directory")
    ex_parser.add_argument("--source-version", help="Source Claude Code version for patch targeting")
    ex_parser.add_argument("--include-sourcemaps", action="store_true", help="Write sourcemap files")
    ex_parser.add_argument("--no-manifest", dest="manifest", action="store_false", help="Skip bundle manifest output")
    ex_parser.set_defaults(manifest=True)

    # Unpack alias
    unpack_parser = subparsers.add_parser("unpack", help="Alias for extract with TypeScript-compatible naming")
    unpack_parser.add_argument("binary", help="Path to Bun standalone binary")
    unpack_parser.add_argument("--out", required=True, help="Output directory")
    unpack_parser.add_argument("--source-version", help="Source Claude Code version for patch targeting")
    unpack_parser.add_argument("--include-sourcemaps", action="store_true", help="Write sourcemap files")
    unpack_parser.add_argument("--manifest", dest="manifest", action="store_true", default=True, help="Write bundle manifest")
    unpack_parser.add_argument("--no-manifest", dest="manifest", action="store_false", help="Skip bundle manifest output")

    # Inspect
    inspect_parser = subparsers.add_parser("inspect", help="Inspect Bun binary metadata")
    inspect_parser.add_argument("binary", help="Path to Bun standalone binary")
    inspect_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")

    # Pack
    pk_parser = subparsers.add_parser("pack", help="Pack directory back into binary")
    pk_parser.add_argument("indir", help="Directory with extracted files and manifest")
    pk_parser.add_argument("base_binary", help="Original binary to use as template")
    pk_parser.add_argument("out_binary", help="Path for output binary")

    # Patch
    patch_parser = subparsers.add_parser("patch", help="Create or apply text patches to extracted bundles")
    patch_subparsers = patch_parser.add_subparsers(dest="patch_command", help="Patch commands")

    patch_init_parser = patch_subparsers.add_parser("init", help="Create a patch scaffold")
    patch_init_parser.add_argument("patch_dir", help="Directory where the patch scaffold will be created")

    patch_apply_parser = patch_subparsers.add_parser("apply", help="Apply a patch to an extracted bundle")
    patch_apply_parser.add_argument("patch_dir", help="Directory containing patch.json")
    patch_apply_parser.add_argument("extract_dir", help="Directory containing extracted bundle files")
    patch_apply_parser.add_argument("--check", action="store_true", help="Validate the patch without writing files")
    patch_apply_parser.add_argument("--binary", help="Path to source binary to derive checksum override")
    patch_apply_parser.add_argument("--source-version", help="Source version override for target validation")

    args = parser.parse_args()

    try:
        if args.command == "download":
            version = resolve_requested_version(args.version, latest=args.latest, npm=args.npm)
            if args.npm:
                download_npm(version, args.outdir)
            else:
                download_binary(version, args.outdir)
        elif args.command == "extract":
            extract_all(
                args.binary,
                args.outdir,
                source_version=args.source_version,
                write_sourcemaps=args.include_sourcemaps,
                manifest=args.manifest,
            )
        elif args.command == "unpack":
            extract_all(
                args.binary,
                args.out,
                source_version=args.source_version,
                write_sourcemaps=args.include_sourcemaps,
                manifest=args.manifest,
            )
        elif args.command == "inspect":
            inspect_binary(args.binary, as_json=args.json)
        elif args.command == "pack":
            pack_bundle(args.indir, args.out_binary, args.base_binary)
        elif args.command == "patch":
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
        else:
            parser.print_help()
    except Exception as e:
        print(f"[!] Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
