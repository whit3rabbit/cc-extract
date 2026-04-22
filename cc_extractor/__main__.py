import argparse
import sys
from .downloader import download_binary, download_npm, resolve_requested_version
from .extractor import extract_all
from .bundler import pack_bundle
from .patcher import init_patch, apply_patch

def main():
    parser = argparse.ArgumentParser(description="Bun Bundle Manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Download
    dl_parser = subparsers.add_parser("download", help="Download binary or NPM bundle")
    dl_parser.add_argument("version", nargs="?", help="Version to download")
    dl_parser.add_argument("--latest", action="store_true", help="Download the latest version without prompting")
    dl_parser.add_argument("--npm", action="store_true", help="Download NPM bundle instead of binary")
    dl_parser.add_argument("--outdir", default="downloads", help="Output directory")

    # Extract
    ex_parser = subparsers.add_parser("extract", help="Extract Bun bundle from binary")
    ex_parser.add_argument("binary", help="Path to Mach-O binary")
    ex_parser.add_argument("outdir", help="Output directory")
    ex_parser.add_argument("--source-version", help="Source Claude Code version for patch targeting")

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
            extract_all(args.binary, args.outdir, source_version=args.source_version)
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
