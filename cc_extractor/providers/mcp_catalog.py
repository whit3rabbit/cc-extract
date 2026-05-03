"""Built-in optional MCP catalog for isolated variants."""

import copy
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class McpCatalogEntry:
    id: str
    name: str
    description: str
    server_name: str
    server: Dict[str, object]
    required_env: Tuple[str, ...] = field(default_factory=tuple)
    auth: str = ""
    source: str = "optional"


OPTIONAL_MCP_CATALOG: Dict[str, McpCatalogEntry] = {
    "notion": McpCatalogEntry(
        id="notion",
        name="Notion",
        description="Connect Claude Code to Notion workspaces. Authenticate with /mcp after launch.",
        server_name="notion",
        server={
            "type": "http",
            "url": "https://mcp.notion.com/mcp",
        },
        auth="oauth",
    ),
    "sentry": McpCatalogEntry(
        id="sentry",
        name="Sentry",
        description="Inspect Sentry errors and production issue context. Authenticate with /mcp after launch.",
        server_name="sentry",
        server={
            "type": "http",
            "url": "https://mcp.sentry.dev/mcp",
        },
        auth="oauth",
    ),
    "github": McpCatalogEntry(
        id="github",
        name="GitHub",
        description="Review repositories, issues, and pull requests through GitHub's remote MCP server.",
        server_name="github",
        server={
            "type": "http",
            "url": "https://api.githubcopilot.com/mcp/",
            "headers": {
                "Authorization": "Bearer ${GITHUB_TOKEN}",
            },
        },
        required_env=("GITHUB_TOKEN",),
        auth="env:GITHUB_TOKEN",
    ),
    "dbhub-postgres": McpCatalogEntry(
        id="dbhub-postgres",
        name="DBHub PostgreSQL",
        description="Query a PostgreSQL database through Bytebase DBHub using DBHUB_POSTGRES_DSN.",
        server_name="dbhub-postgres",
        server={
            "type": "stdio",
            "command": "npx",
            "args": [
                "-y",
                "@bytebase/dbhub",
                "--dsn",
                "${DBHUB_POSTGRES_DSN}",
            ],
        },
        required_env=("DBHUB_POSTGRES_DSN",),
        auth="env:DBHUB_POSTGRES_DSN",
    ),
}


PLUGIN_RECOMMENDATIONS = [
    "github",
    "linear",
    "figma",
    "sentry",
    "pyright-lsp",
    "typescript-lsp",
]


def list_optional_mcp_entries() -> List[McpCatalogEntry]:
    return [OPTIONAL_MCP_CATALOG[key] for key in sorted(OPTIONAL_MCP_CATALOG)]


def normalize_mcp_ids(ids: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    for raw_id in ids:
        mcp_id = str(raw_id or "").strip()
        if not mcp_id:
            continue
        if mcp_id not in OPTIONAL_MCP_CATALOG:
            raise ValueError(f"Unknown MCP server id: {mcp_id}")
        if mcp_id not in normalized:
            normalized.append(mcp_id)
    return normalized


def optional_mcp_servers(ids: Iterable[str]) -> Dict[str, object]:
    servers = {}
    for mcp_id in normalize_mcp_ids(ids):
        entry = OPTIONAL_MCP_CATALOG[mcp_id]
        servers[entry.server_name] = copy.deepcopy(entry.server)
    return servers


def mcp_entry_payload(entry: McpCatalogEntry) -> Dict[str, object]:
    return {
        "id": entry.id,
        "name": entry.name,
        "description": entry.description,
        "serverName": entry.server_name,
        "requiredEnv": list(entry.required_env),
        "auth": entry.auth,
        "source": entry.source,
        "server": copy.deepcopy(entry.server),
    }


def list_mcp_catalog(*, provider_key: str = "") -> Dict[str, object]:
    from .loader import get_provider, list_providers

    providers = [get_provider(provider_key)] if provider_key else list_providers()
    provider_entries = []
    for provider in providers:
        for server_name, server in sorted(provider.mcp_servers.items()):
            provider_entries.append({
                "id": server_name,
                "name": server_name,
                "description": f"{provider.label} provider-owned MCP server",
                "providerKey": provider.key,
                "providerLabel": provider.label,
                "serverName": server_name,
                "source": "provider",
                "autoEnabled": True,
                "server": copy.deepcopy(server),
            })

    return {
        "providerMcpServers": provider_entries,
        "optionalMcpServers": [mcp_entry_payload(entry) for entry in list_optional_mcp_entries()],
        "pluginRecommendations": list(PLUGIN_RECOMMENDATIONS),
    }
