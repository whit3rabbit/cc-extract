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
from .schema import DEFAULT_TIMEOUT_MS, MODEL_ENV_KEYS, ProviderEnv, ProviderSchemaError, ProviderTemplate

__all__ = [
    "DEFAULT_TIMEOUT_MS",
    "MODEL_ENV_KEYS",
    "PLACEHOLDER_CREDENTIAL",
    "ProviderConfigResult",
    "ProviderEnv",
    "ProviderSchemaError",
    "ProviderTemplate",
    "apply_provider_claude_config",
    "build_provider_env",
    "get_provider",
    "list_providers",
    "provider_claude_config",
    "provider_default_variant_name",
    "provider_patch_config",
    "provider_prompt_overlays",
    "provider_theme",
]
