"""Apply provider-specific Claude config merges (settings + MCP servers)."""

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .._utils import atomic_write_text_no_symlink
from .loader import get_provider
from .mcp_catalog import optional_mcp_servers


PLACEHOLDER_CREDENTIAL = "Enter your API key"


@dataclass(frozen=True)
class ProviderConfigResult:
    settings_changed: bool
    claude_config_changed: bool


def apply_provider_claude_config(
    provider_key: str,
    config_dir,
    *,
    credential_value: Optional[str] = None,
    optional_mcp_ids=None,
    read_json=None,
    write_json=None,
) -> ProviderConfigResult:
    provider = get_provider(provider_key)
    config_dir = Path(config_dir)
    settings_changed = _merge_settings_permissions(
        config_dir,
        provider.settings_permissions_deny,
        read_json=read_json,
        write_json=write_json,
    )
    mcp_servers = dict(provider.mcp_servers)
    mcp_servers.update(optional_mcp_servers(optional_mcp_ids or []))
    claude_config_changed = _merge_mcp_servers(
        config_dir,
        mcp_servers,
        credential_value=credential_value,
        read_json=read_json,
        write_json=write_json,
    )
    return ProviderConfigResult(settings_changed, claude_config_changed)


def _merge_settings_permissions(config_dir: Path, deny_tools, *, read_json, write_json) -> bool:
    if not deny_tools:
        return False
    settings_path = config_dir / "settings.json"
    existing = _read(settings_path, read_json)
    permissions = dict(existing.get("permissions") or {})
    deny = list(permissions.get("deny") or [])

    changed = False
    for tool in deny_tools:
        if tool not in deny:
            deny.append(tool)
            changed = True
    if not changed:
        return False

    permissions["deny"] = deny
    existing["permissions"] = permissions
    _write(settings_path, existing, write_json)
    return True


def _merge_mcp_servers(config_dir: Path, servers: Dict[str, object], *, credential_value, read_json, write_json) -> bool:
    if not servers:
        return False
    config_path = config_dir / ".claude.json"
    existing = _read(config_path, read_json)
    existing_servers = dict(existing.get("mcpServers") or {})

    changed = False
    for name, server in servers.items():
        if name in existing_servers:
            continue
        existing_servers[name] = _replace_credential(copy.deepcopy(server), PLACEHOLDER_CREDENTIAL)
        changed = True
    if not changed:
        return False

    existing["mcpServers"] = existing_servers
    _write(config_path, existing, write_json)
    return True


def _replace_credential(value, credential: str):
    if isinstance(value, str):
        return value.replace("${credential}", credential)
    if isinstance(value, list):
        return [_replace_credential(item, credential) for item in value]
    if isinstance(value, dict):
        return {key: _replace_credential(item, credential) for key, item in value.items()}
    return value


def _read(path: Path, read_json):
    if read_json is None:
        if not path.exists():
            return {}
        return read_json_default(path)
    if not path.exists():
        return {}
    return read_json(path)


def _write(path: Path, payload, write_json):
    path.parent.mkdir(parents=True, exist_ok=True)
    if write_json is None:
        write_json_default(path, payload)
    else:
        write_json(path, payload)


def read_json_default(path: Path):
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def write_json_default(path: Path, payload) -> None:
    import json

    atomic_write_text_no_symlink(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
