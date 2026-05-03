"""Provider templates and env builders for alternate Claude Code backends."""

from .config import PLACEHOLDER_CREDENTIAL, ProviderConfigResult, apply_provider_claude_config
from .loader import (
    build_provider_env,
    get_provider,
    list_providers,
    provider_claude_config,
    provider_default_variant_name,
    provider_patch_config,
    provider_prompt_overlays,
    provider_theme,
)
from .mcp_catalog import (
    PLUGIN_RECOMMENDATIONS,
    McpCatalogEntry,
    list_mcp_catalog,
    list_optional_mcp_entries,
    mcp_entry_payload,
    normalize_mcp_ids,
    optional_mcp_servers,
)
from .schema import DEFAULT_TIMEOUT_MS, MODEL_ENV_KEYS, ProviderEnv, ProviderSchemaError, ProviderTemplate

__all__ = [
    "DEFAULT_TIMEOUT_MS",
    "MODEL_ENV_KEYS",
    "PLACEHOLDER_CREDENTIAL",
    "PLUGIN_RECOMMENDATIONS",
    "McpCatalogEntry",
    "ProviderConfigResult",
    "ProviderEnv",
    "ProviderSchemaError",
    "ProviderTemplate",
    "apply_provider_claude_config",
    "build_provider_env",
    "get_provider",
    "list_mcp_catalog",
    "list_optional_mcp_entries",
    "list_providers",
    "mcp_entry_payload",
    "normalize_mcp_ids",
    "optional_mcp_servers",
    "provider_claude_config",
    "provider_default_variant_name",
    "provider_patch_config",
    "provider_prompt_overlays",
    "provider_theme",
]
