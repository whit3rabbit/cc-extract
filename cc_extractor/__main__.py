"""Top-level CLI entry point.

The argparse parser tree is built in :mod:`cc_extractor.cli.parsers`; simple
non-variant subcommand handlers live in :mod:`cc_extractor.cli.handlers`. The
variant subcommand dispatcher and the ``main`` entry point live here so test
fixtures can monkey-patch variant helpers (``create_variant``, ``load_variant``,
``doctor_variant``, ``remove_variant``, etc.) via ``cc_extractor.__main__`` and
have those patches apply to the dispatch site.
"""

import sys

from .cli import build_parser, inspect_binary  # noqa: F401 — re-exported for test imports
from .cli import handlers as _handlers
from .providers import list_mcp_catalog
from .cli.payloads import (
    model_overrides_from_args,
    print_json,
    tweak_options_from_args,
    variant_payload,
    variant_result_payload,
)
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


_SIMPLE_HANDLERS = {
    "download": _handlers.cmd_download,
    "extract": _handlers.cmd_extract,
    "unpack": _handlers.cmd_unpack,
    "inspect": _handlers.cmd_inspect,
    "replace-entry": _handlers.cmd_replace_entry,
    "apply-binary": _handlers.cmd_apply_binary,
    "pack": _handlers.cmd_pack,
}


def cmd_variant(args, variant_parser):
    """Dispatch ``variant <subcommand>`` against the variant helpers above.

    Names like ``create_variant`` are looked up via this module's globals so
    test fixtures that ``monkeypatch.setattr(cli, "create_variant", fake)``
    take effect.
    """
    sub = args.variant_command
    if sub == "providers":
        providers = list_variant_providers()
        if args.json:
            print_json(providers)
        else:
            for provider in providers:
                print(f"{provider['key']}: {provider['label']} - {provider['description']}")
    elif sub == "mcp":
        catalog = list_mcp_catalog(provider_key=args.provider or "")
        if args.json:
            print_json(catalog)
        else:
            print("Provider MCP servers:")
            for item in catalog["providerMcpServers"]:
                provider = item.get("providerKey") or "?"
                print(f"    {provider}:{item['id']} auto-enabled")
            print("Optional MCP servers:")
            for item in catalog["optionalMcpServers"]:
                env = ", ".join(item.get("requiredEnv") or [])
                suffix = f" env:{env}" if env else ""
                print(f"    {item['id']}: {item['name']}{suffix}")
            print("Plugin recommendations:")
            print("    " + ", ".join(catalog["pluginRecommendations"]))
    elif sub == "create":
        result = create_variant(
            name=args.name,
            provider_key=args.provider,
            claude_version=args.claude_version,
            patch_profile_id=args.patch_profile,
            tweaks=args.tweak,
            base_url=args.base_url,
            credential_env=args.credential_env,
            api_key=args.api_key,
            store_secret=args.store_secret,
            bin_dir=args.bin_dir,
            force=args.force,
            model_overrides=model_overrides_from_args(args),
            extra_env=args.extra_env,
            tweak_options=tweak_options_from_args(args),
            mcp_ids=args.mcp,
        )
        if args.json:
            print_json(variant_result_payload(result))
        else:
            print(f"[+] Variant created: {result.variant.variant_id}")
            print(f"    binary: {result.binary_path}")
            print(f"    wrapper: {result.wrapper_path}")
    elif sub == "list":
        variants = scan_variants()
        if args.json:
            print_json([variant_payload(variant) for variant in variants])
        else:
            for variant in variants:
                source = variant.manifest.get("source", {})
                provider = variant.manifest.get("provider", {})
                print(
                    f"{variant.variant_id}: {provider.get('key')} {source.get('version')} "
                    f"-> {variant.manifest.get('paths', {}).get('wrapper')}"
                )
    elif sub == "show":
        variant = load_variant(args.name)
        print_json(variant_payload(variant))
    elif sub == "apply":
        result = apply_variant(args.name)
        if args.json:
            print_json(variant_result_payload(result))
        else:
            print(f"[+] Variant applied: {result.variant.variant_id}")
            print(f"    wrapper: {result.wrapper_path}")
    elif sub == "update":
        results = update_variants(
            args.name,
            all_variants=args.all,
            claude_version=args.claude_version,
        )
        if args.json:
            print_json([variant_result_payload(result) for result in results])
        else:
            for result in results:
                print(f"[+] Variant updated: {result.variant.variant_id}")
    elif sub == "remove":
        removed = remove_variant(args.name, yes=args.yes)
        print(f"[+] Removed variant: {args.name}" if removed else f"[*] No variant found: {args.name}")
    elif sub == "doctor":
        report = doctor_variant(args.name, all_variants=args.all)
        if args.json:
            print_json(report)
        else:
            for item in report:
                status = "ok" if item["ok"] else "failed"
                print(f"{item['id']}: {status}")
                for check in item["checks"]:
                    mark = "ok" if check["ok"] else "missing"
                    print(f"    {check['name']}: {mark} {check['path']}")
    elif sub == "run":
        variant_args = list(args.variant_args or [])
        if variant_args and variant_args[0] == "--":
            variant_args = variant_args[1:]
        sys.exit(run_variant(args.name, variant_args))
    else:
        variant_parser.print_help()


def main():
    parser, patch_parser, variant_parser = build_parser()

    if len(sys.argv) == 1:
        if sys.stdin.isatty() and sys.stdout.isatty():
            from .tui import run_tui

            try:
                run_tui()
            except Exception as exc:
                print(f"[!] Error: {exc}")
                sys.exit(1)
            return
        parser.print_help()
        return

    args = parser.parse_args()

    try:
        if args.command in _SIMPLE_HANDLERS:
            _SIMPLE_HANDLERS[args.command](args)
        elif args.command == "patch":
            _handlers.cmd_patch(args, patch_parser)
        elif args.command == "variant":
            cmd_variant(args, variant_parser)
        else:
            parser.print_help()
    except Exception as exc:
        print(f"[!] Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
