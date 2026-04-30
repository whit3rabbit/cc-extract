import argparse
from dataclasses import asdict, is_dataclass
import json
import sys
from pathlib import Path

from .bun_extract import parse_bun_binary
from .binary_patcher import PatchInputs, apply_patches, replace_entry_js
from .downloader import download_binary, download_npm, resolve_requested_version
from .extractor import extract_all
from .bundler import pack_bundle
from .patcher import init_patch, apply_patch
from .variants import (
    apply_variant,
    create_variant,
    doctor_variant,
    list_variant_providers,
    load_variant,
    remove_variant,
    run_variant,
    scan_variants,
    update_variants,
)


def _to_jsonable(value):
    if is_dataclass(value):
        return asdict(value)
    return value


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


def _print_json(payload):
    print(json.dumps(payload, indent=2, sort_keys=True))


def _variant_payload(variant):
    return dict(variant.manifest)


def _variant_result_payload(result):
    payload = dict(result.variant.manifest)
    payload["build"] = {
        "binaryPath": str(result.binary_path),
        "wrapperPath": str(result.wrapper_path),
        "outputSha256": result.output_sha256,
        "appliedTweaks": result.applied_tweaks,
        "skippedTweaks": result.skipped_tweaks,
        "missingPromptKeys": result.missing_prompt_keys,
    }
    return payload


def _model_overrides_from_args(args):
    return {
        "sonnet": getattr(args, "model_sonnet", None),
        "opus": getattr(args, "model_opus", None),
        "haiku": getattr(args, "model_haiku", None),
        "small_fast": getattr(args, "model_small_fast", None),
        "default": getattr(args, "model_default", None),
        "subagent": getattr(args, "subagent_model", None),
    }


def _tweak_options_from_args(args):
    return {
        "context_limit": getattr(args, "context_limit", None),
        "file_read_limit": getattr(args, "file_read_limit", None),
        "subagent_model": getattr(args, "subagent_model", None),
    }


def _add_variant_model_args(parser):
    parser.add_argument("--model-sonnet", help="Provider model mapped to Sonnet")
    parser.add_argument("--model-opus", help="Provider model mapped to Opus")
    parser.add_argument("--model-haiku", help="Provider model mapped to Haiku")
    parser.add_argument("--model-small-fast", help="Provider small/fast model")
    parser.add_argument("--model-default", help="Provider startup/default model")
    parser.add_argument("--subagent-model", help="Provider subagent model")


def _add_variant_tweak_option_args(parser):
    parser.add_argument("--context-limit", help="CLAUDE_CODE_CONTEXT_LIMIT value for context-limit tweak")
    parser.add_argument("--file-read-limit", help="CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS value")


def main():
    parser = argparse.ArgumentParser(description="Bun standalone binary manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Download
    dl_parser = subparsers.add_parser("download", help="Download binary or NPM bundle")
    dl_parser.add_argument("version", nargs="?", help="Version to download")
    dl_parser.add_argument("--latest", action="store_true", help="Download the latest version without prompting")
    dl_parser.add_argument("--npm", action="store_true", help="Download NPM bundle instead of binary")
    dl_parser.add_argument("--outdir", help="Output directory")

    # Extract
    ex_parser = subparsers.add_parser("extract", help="Extract Bun bundle from binary")
    ex_parser.add_argument("binary", help="Path to Bun standalone binary")
    ex_parser.add_argument("outdir", nargs="?", help="Output directory")
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

    # Replace entry
    replace_entry_parser = subparsers.add_parser("replace-entry", help="Replace the entry JS module and repack")
    replace_entry_parser.add_argument("binary", help="Path to Bun standalone binary")
    replace_entry_parser.add_argument("entry_js", help="Path to replacement entry JS")
    replace_entry_parser.add_argument("--out", required=True, help="Output binary path")

    # Apply binary theme/prompt patches
    apply_binary_parser = subparsers.add_parser("apply-binary", help="Apply theme and prompt patches to a binary")
    apply_binary_parser.add_argument("binary", help="Path to Bun standalone binary to patch in place")
    apply_binary_parser.add_argument("--config", required=True, help="Config JSON containing settings.themes")
    apply_binary_parser.add_argument("--overlays", help="Prompt overlay JSON")

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

    # Variant manager
    variant_parser = subparsers.add_parser("variant", help="Create and manage isolated Claude Code variants")
    variant_subparsers = variant_parser.add_subparsers(dest="variant_command", help="Variant commands")

    variant_providers = variant_subparsers.add_parser("providers", help="List provider presets")
    variant_providers.add_argument("--json", action="store_true", help="Print machine-readable JSON")

    variant_create = variant_subparsers.add_parser("create", help="Create an isolated variant")
    variant_create.add_argument("--name", required=True, help="Variant name, also used as wrapper command")
    variant_create.add_argument("--provider", required=True, help="Provider preset key")
    variant_create.add_argument("--claude-version", default="latest", help="Claude Code version, latest, or stable")
    variant_create.add_argument("--patch-profile", help="Patch profile id to apply")
    variant_create.add_argument("--tweak", action="append", help="Curated tweak id, repeatable")
    variant_create.add_argument("--credential-env", help="Environment variable containing provider credentials")
    variant_create.add_argument("--api-key", help="Provider credential to store locally, requires --store-secret")
    variant_create.add_argument("--store-secret", action="store_true", help="Store --api-key in variant-local secrets.env")
    variant_create.add_argument("--bin-dir", help="Wrapper output directory")
    variant_create.add_argument("--force", action="store_true", help="Overwrite an existing variant")
    variant_create.add_argument("--extra-env", action="append", help="Additional KEY=VALUE env entry, repeatable")
    variant_create.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    _add_variant_model_args(variant_create)
    _add_variant_tweak_option_args(variant_create)

    variant_list = variant_subparsers.add_parser("list", help="List variants")
    variant_list.add_argument("--json", action="store_true", help="Print machine-readable JSON")

    variant_show = variant_subparsers.add_parser("show", help="Show variant metadata")
    variant_show.add_argument("name", help="Variant name or id")
    variant_show.add_argument("--json", action="store_true", help="Print machine-readable JSON")

    variant_apply = variant_subparsers.add_parser("apply", help="Re-apply a variant using its saved settings")
    variant_apply.add_argument("name", help="Variant name or id")
    variant_apply.add_argument("--json", action="store_true", help="Print machine-readable JSON")

    variant_update = variant_subparsers.add_parser("update", help="Update one or all variants")
    variant_update.add_argument("name", nargs="?", help="Variant name or id")
    variant_update.add_argument("--all", action="store_true", help="Update all variants")
    variant_update.add_argument("--claude-version", help="Override Claude Code version")
    variant_update.add_argument("--json", action="store_true", help="Print machine-readable JSON")

    variant_remove = variant_subparsers.add_parser("remove", help="Remove a variant")
    variant_remove.add_argument("name", help="Variant name or id")
    variant_remove.add_argument("--yes", action="store_true", help="Confirm removal")

    variant_doctor = variant_subparsers.add_parser("doctor", help="Health check variants")
    variant_doctor.add_argument("name", nargs="?", help="Variant name or id")
    variant_doctor.add_argument("--all", action="store_true", help="Check all variants")
    variant_doctor.add_argument("--json", action="store_true", help="Print machine-readable JSON")

    variant_run = variant_subparsers.add_parser("run", help="Run a variant wrapper")
    variant_run.add_argument("name", help="Variant name or id")
    variant_run.add_argument("variant_args", nargs=argparse.REMAINDER, help="Arguments passed to Claude Code")

    if len(sys.argv) == 1:
        if sys.stdin.isatty() and sys.stdout.isatty():
            from .tui import run_tui

            try:
                run_tui()
            except Exception as e:
                print(f"[!] Error: {e}")
                sys.exit(1)
            return
        parser.print_help()
        return

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
        elif args.command == "replace-entry":
            data = Path(args.binary).read_bytes()
            info = parse_bun_binary(data)
            new_content = Path(args.entry_js).read_bytes()
            result = replace_entry_js(data, info, new_content)
            out_path = Path(args.out)
            out_path.write_bytes(result.buf)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "delta": result.delta,
                        "signatureInvalidated": result.signature_invalidated,
                        "signatureStripped": result.signature_stripped,
                        "out": str(out_path),
                    },
                    indent=2,
                )
            )
        elif args.command == "apply-binary":
            config = json.loads(Path(args.config).read_text(encoding="utf-8"))
            overlays = None
            if args.overlays:
                overlays = json.loads(Path(args.overlays).read_text(encoding="utf-8"))
            result = apply_patches(PatchInputs(binary_path=args.binary, config=config, overlays=overlays))
            print(json.dumps(_to_jsonable(result), indent=2))
            if not result.ok:
                sys.exit(1)
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
        elif args.command == "variant":
            if args.variant_command == "providers":
                providers = list_variant_providers()
                if args.json:
                    _print_json(providers)
                else:
                    for provider in providers:
                        print(f"{provider['key']}: {provider['label']} - {provider['description']}")
            elif args.variant_command == "create":
                result = create_variant(
                    name=args.name,
                    provider_key=args.provider,
                    claude_version=args.claude_version,
                    patch_profile_id=args.patch_profile,
                    tweaks=args.tweak,
                    credential_env=args.credential_env,
                    api_key=args.api_key,
                    store_secret=args.store_secret,
                    bin_dir=args.bin_dir,
                    force=args.force,
                    model_overrides=_model_overrides_from_args(args),
                    extra_env=args.extra_env,
                    tweak_options=_tweak_options_from_args(args),
                )
                if args.json:
                    _print_json(_variant_result_payload(result))
                else:
                    print(f"[+] Variant created: {result.variant.variant_id}")
                    print(f"    binary: {result.binary_path}")
                    print(f"    wrapper: {result.wrapper_path}")
            elif args.variant_command == "list":
                variants = scan_variants()
                if args.json:
                    _print_json([_variant_payload(variant) for variant in variants])
                else:
                    for variant in variants:
                        source = variant.manifest.get("source", {})
                        provider = variant.manifest.get("provider", {})
                        print(f"{variant.variant_id}: {provider.get('key')} {source.get('version')} -> {variant.manifest.get('paths', {}).get('wrapper')}")
            elif args.variant_command == "show":
                variant = load_variant(args.name)
                if args.json:
                    _print_json(_variant_payload(variant))
                else:
                    _print_json(_variant_payload(variant))
            elif args.variant_command == "apply":
                result = apply_variant(args.name)
                if args.json:
                    _print_json(_variant_result_payload(result))
                else:
                    print(f"[+] Variant applied: {result.variant.variant_id}")
                    print(f"    wrapper: {result.wrapper_path}")
            elif args.variant_command == "update":
                results = update_variants(
                    args.name,
                    all_variants=args.all,
                    claude_version=args.claude_version,
                )
                if args.json:
                    _print_json([_variant_result_payload(result) for result in results])
                else:
                    for result in results:
                        print(f"[+] Variant updated: {result.variant.variant_id}")
            elif args.variant_command == "remove":
                removed = remove_variant(args.name, yes=args.yes)
                print(f"[+] Removed variant: {args.name}" if removed else f"[*] No variant found: {args.name}")
            elif args.variant_command == "doctor":
                report = doctor_variant(args.name, all_variants=args.all)
                if args.json:
                    _print_json(report)
                else:
                    for item in report:
                        status = "ok" if item["ok"] else "failed"
                        print(f"{item['id']}: {status}")
                        for check in item["checks"]:
                            mark = "ok" if check["ok"] else "missing"
                            print(f"    {check['name']}: {mark} {check['path']}")
            elif args.variant_command == "run":
                variant_args = list(args.variant_args or [])
                if variant_args and variant_args[0] == "--":
                    variant_args = variant_args[1:]
                sys.exit(run_variant(args.name, variant_args))
            else:
                variant_parser.print_help()
        else:
            parser.print_help()
    except Exception as e:
        print(f"[!] Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
