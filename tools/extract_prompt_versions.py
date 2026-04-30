#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cc_extractor.bun_extract import parse_bun_binary
from cc_extractor.bun_extract.extract import extract_all as extract_bun_modules
from cc_extractor.downloader import download_binary, list_available_binary_versions

from tools.prompt_extractor import extract_prompts


PromptData = Dict[str, Any]
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass
class VersionResult:
    version: str
    ok: bool
    output_path: Optional[Path] = None
    prompt_count: int = 0
    error: Optional[str] = None


def prompt_output_path(prompts_dir: Path, version: str) -> Path:
    return prompts_dir / f"{version}.json"


def bundled_cli_path(extract_dir: Path) -> Path:
    manifest_path = extract_dir / ".bundle_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry_point = manifest.get("entryPoint")
        if entry_point:
            candidate = extract_dir / entry_point
            if candidate.exists():
                return candidate

    candidate = extract_dir / "src" / "entrypoints" / "cli.js"
    if candidate.exists():
        return candidate

    raise FileNotFoundError(f"Could not locate cli.js in {extract_dir}")


def catalog_path(catalog_dir: Optional[Path], version: str) -> Optional[Path]:
    if catalog_dir is None:
        return None
    candidate = catalog_dir / f"prompts-{version}.json"
    return candidate if candidate.exists() else None


def load_existing_prompts(path: Optional[Path]) -> List[Dict[str, Any]]:
    if path is None or not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("prompts", [])


def validate_prompt_data(data: PromptData, expected_version: str) -> None:
    if not isinstance(data, dict):
        raise ValueError("prompt data must be a JSON object")
    if data.get("version") != expected_version:
        raise ValueError(
            f"version mismatch: expected {expected_version}, got {data.get('version')!r}"
        )

    prompts = data.get("prompts")
    if not isinstance(prompts, list):
        raise ValueError("prompts must be a list")
    if not prompts:
        raise ValueError("prompts must not be empty")

    for index, prompt in enumerate(prompts):
        validate_prompt(prompt, index)


def validate_prompt(prompt: Dict[str, Any], index: int) -> None:
    required = {
        "name",
        "id",
        "description",
        "pieces",
        "identifiers",
        "identifierMap",
        "version",
    }
    missing = required - set(prompt)
    if missing:
        raise ValueError(f"prompt {index} missing keys: {sorted(missing)}")

    for key in ("name", "id", "description"):
        if not isinstance(prompt[key], str):
            raise ValueError(f"prompt {index} {key} must be a string")

    pieces = prompt["pieces"]
    identifiers = prompt["identifiers"]
    identifier_map = prompt["identifierMap"]

    if not isinstance(pieces, list) or not all(isinstance(piece, str) for piece in pieces):
        raise ValueError(f"prompt {index} pieces must be a list of strings")
    if not pieces:
        raise ValueError(f"prompt {index} pieces must not be empty")
    if not isinstance(identifiers, list) or not all(isinstance(item, int) for item in identifiers):
        raise ValueError(f"prompt {index} identifiers must be a list of integers")
    if len(pieces) != len(identifiers) + 1:
        raise ValueError(
            f"prompt {index} pieces length must equal identifiers length plus one"
        )
    if not isinstance(identifier_map, dict):
        raise ValueError(f"prompt {index} identifierMap must be an object")
    if not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in identifier_map.items()
    ):
        raise ValueError(f"prompt {index} identifierMap must map strings to strings")
    if not isinstance(prompt["version"], str) and prompt["version"] is not None:
        raise ValueError(f"prompt {index} version must be a string or null")


def write_validated_prompt_data(data: PromptData, output_path: Path, expected_version: str) -> None:
    validate_prompt_data(data, expected_version)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=output_path.parent,
        delete=False,
    ) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    temp_path.replace(output_path)

    written = json.loads(output_path.read_text(encoding="utf-8"))
    validate_prompt_data(written, expected_version)


def extract_binary(binary_path: Path, extract_dir: Path, version: str, force: bool = False) -> Path:
    cli_path = extract_dir / "src" / "entrypoints" / "cli.js"
    manifest_path = extract_dir / ".bundle_manifest.json"
    if not force and cli_path.exists() and manifest_path.exists():
        return bundled_cli_path(extract_dir)

    if force and extract_dir.exists():
        shutil.rmtree(extract_dir)

    data = binary_path.read_bytes()
    info = parse_bun_binary(data)
    extract_bun_modules(data, info, extract_dir, manifest=True)
    (extract_dir / ".bundle_source.json").write_text(
        json.dumps({"binary": str(binary_path), "sourceVersion": version}, indent=2) + "\n",
        encoding="utf-8",
    )
    return bundled_cli_path(extract_dir)


def extract_version_prompts(
    version: str,
    prompts_dir: Path,
    download_dir: Path,
    work_dir: Path,
    catalog_dir_value: Optional[Path] = None,
    force_download: bool = False,
    force_extract: bool = False,
    force_prompts: bool = False,
) -> VersionResult:
    output_path = prompt_output_path(prompts_dir, version)
    if output_path.exists() and not force_prompts:
        data = json.loads(output_path.read_text(encoding="utf-8"))
        validate_prompt_data(data, version)
        return VersionResult(version, True, output_path, len(data["prompts"]))

    binary_name = "claude.exe" if sys.platform.startswith("win") else "claude"
    binary_path = download_dir / version / binary_name
    if force_download and binary_path.exists():
        binary_path.unlink()
    binary_path = Path(download_binary(version, str(download_dir)))

    extract_dir = work_dir / version / "extracted"
    cli_path = extract_binary(binary_path, extract_dir, version, force=force_extract)
    existing_path = (
        output_path if output_path.exists() else catalog_path(catalog_dir_value, version)
    )
    data = extract_prompts(
        str(cli_path),
        version=version,
        existing_prompts=load_existing_prompts(existing_path),
    )
    write_validated_prompt_data(data, output_path, version)
    return VersionResult(version, True, output_path, len(data["prompts"]))


def local_versions(download_dir: Path) -> List[str]:
    versions = []
    for binary in download_dir.glob("*/claude"):
        versions.append(binary.parent.name)
    for binary in download_dir.glob("*/claude.exe"):
        versions.append(binary.parent.name)
    return sort_versions(versions)


def is_version(value: str) -> bool:
    return bool(VERSION_RE.match(value))


def sort_versions(versions: Iterable[str]) -> List[str]:
    def key(version: str) -> Tuple[int, ...]:
        parts = []
        for part in version.split("."):
            try:
                parts.append(int(part))
            except ValueError:
                parts.append(-1)
        return tuple(parts)

    return sorted({version for version in versions if is_version(version)}, key=key, reverse=True)


def resolve_versions(args: argparse.Namespace) -> List[str]:
    if args.versions:
        return sort_versions(args.versions)
    if args.local:
        return local_versions(args.download_dir)
    if args.all:
        return sort_versions(list_available_binary_versions())
    raise ValueError("Pass --versions, --local, or --all")


def run_versions(args: argparse.Namespace) -> List[VersionResult]:
    versions = resolve_versions(args)
    if args.max_versions is not None:
        versions = versions[: args.max_versions]

    results = []
    for version in versions:
        print(f"[*] Extracting prompts for {version}")
        try:
            result = extract_version_prompts(
                version,
                args.prompts_dir,
                args.download_dir,
                args.work_dir,
                catalog_dir_value=args.catalog_dir,
                force_download=args.force_download,
                force_extract=args.force_extract,
                force_prompts=args.force_prompts,
            )
            print(f"[+] {version}: {result.prompt_count} prompts -> {result.output_path}")
        except Exception as exc:
            result = VersionResult(version, False, error=str(exc))
            print(f"[!] {version}: {exc}", file=sys.stderr)
            if args.stop_on_error:
                results.append(result)
                break
        results.append(result)

    return results


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract prompt JSON files to prompts/<version>.json"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--all", action="store_true", help="Process all available binary versions")
    source.add_argument(
        "--local",
        action="store_true",
        help="Process versions already in --download-dir",
    )
    source.add_argument("--versions", nargs="+", help="Specific versions to process")
    parser.add_argument("--max-versions", type=int, help="Limit processed version count")
    parser.add_argument("--prompts-dir", type=Path, default=Path("prompts"))
    parser.add_argument("--download-dir", type=Path, default=Path("downloads"))
    parser.add_argument("--work-dir", type=Path, default=Path("downloads"))
    parser.add_argument(
        "--catalog-dir",
        type=Path,
        default=Path("vendor/tweakcc/data/prompts"),
        help="Existing prompt catalog directory for metadata and short-prompt recovery",
    )
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--force-extract", action="store_true")
    parser.add_argument("--force-prompts", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args(argv)

    results = run_versions(args)
    failed = [result for result in results if not result.ok]
    print(f"[*] Complete: {len(results) - len(failed)} ok, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
