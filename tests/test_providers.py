import json

import pytest

from cc_extractor.providers import (
    PLACEHOLDER_CREDENTIAL,
    apply_provider_claude_config,
    build_provider_env,
    get_provider,
    list_providers,
    provider_patch_config,
    provider_prompt_overlays,
)


def test_provider_list_includes_cc_mirror_parity_presets():
    keys = [provider.key for provider in list_providers()]

    assert keys == [
        "kimi",
        "minimax",
        "zai",
        "deepseek",
        "alibaba",
        "poe",
        "openrouter",
        "vercel",
        "ollama",
        "nanogpt",
        "ccrouter",
        "cerebras",
        "mirror",
        "gatewayz",
        "custom",
    ]


def test_zai_defaults_to_env_ref_without_storing_secret():
    result = build_provider_env("zai")

    assert result.credential == {
        "mode": "env",
        "source": "Z_AI_API_KEY",
        "targets": ["ANTHROPIC_API_KEY", "Z_AI_API_KEY"],
    }
    assert result.secret_env == {}
    assert result.env["ANTHROPIC_BASE_URL"] == "https://api.z.ai/api/anthropic"
    assert result.env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "glm-5.1"
    assert result.env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "glm-5-turbo"
    assert result.env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "glm-4.5-air"
    assert "ANTHROPIC_API_KEY" not in result.env


def test_stored_secret_is_separate_from_safe_env():
    result = build_provider_env("zai", api_key="secret-value", store_secret=True)

    assert result.credential["mode"] == "stored"
    assert result.secret_env == {
        "ANTHROPIC_API_KEY": "secret-value",
        "Z_AI_API_KEY": "secret-value",
    }
    assert "secret-value" not in json.dumps(result.env)


def test_api_key_requires_store_secret():
    with pytest.raises(ValueError, match="--store-secret"):
        build_provider_env("zai", api_key="secret-value")


def test_model_mapping_providers_require_core_model_overrides():
    with pytest.raises(ValueError, match="requires model mapping"):
        build_provider_env("openrouter")

    result = build_provider_env(
        "openrouter",
        model_overrides={
            "sonnet": "anthropic/claude-sonnet-4",
            "opus": "anthropic/claude-opus-4",
            "haiku": "anthropic/claude-haiku-4",
        },
    )

    assert result.env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "anthropic/claude-sonnet-4"


def test_provider_patch_assets_are_safe_and_prompt_pack_skips_mirror():
    config = provider_patch_config("zai")
    assert config["settings"]["themes"][0]["id"] == "zai-variant"
    assert provider_prompt_overlays("mirror") == {}
    assert provider_prompt_overlays("deepseek") == {}
    assert "webfetch" in provider_prompt_overlays("zai")


def test_ported_provider_defaults_match_cc_mirror_update():
    minimax = build_provider_env("minimax")
    assert minimax.env["ANTHROPIC_MODEL"] == "MiniMax-M2.7"
    assert minimax.env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "MiniMax-M2.7"

    deepseek = build_provider_env("deepseek")
    assert deepseek.env["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert deepseek.env["ANTHROPIC_MODEL"] == "deepseek-v4-pro"
    assert deepseek.env["ANTHROPIC_SMALL_FAST_MODEL"] == "deepseek-v4-flash"

    alibaba = build_provider_env("alibaba")
    assert alibaba.env["ANTHROPIC_BASE_URL"] == "https://coding-intl.dashscope.aliyuncs.com/apps/anthropic"
    assert alibaba.env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "qwen3-coder-plus"
    assert alibaba.env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "qwen3.5-plus"
    assert alibaba.env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "qwen3-coder-next"

    poe = build_provider_env("poe")
    assert poe.credential["source"] == "POE_API_KEY"
    assert poe.credential["targets"] == ["ANTHROPIC_AUTH_TOKEN"]
    assert poe.env["ANTHROPIC_BASE_URL"] == "https://api.poe.com"


def test_ccrouter_and_cerebras_use_optional_router_fallbacks():
    ccrouter = build_provider_env("ccrouter")
    assert ccrouter.credential == {"mode": "none", "targets": []}
    assert ccrouter.env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:3456"
    assert ccrouter.env["ANTHROPIC_AUTH_TOKEN"] == "ccrouter-proxy"

    cerebras = build_provider_env("cerebras")
    assert cerebras.credential == {"mode": "none", "targets": []}
    assert cerebras.env["ANTHROPIC_AUTH_TOKEN"] == "cerebras-proxy"
    assert cerebras.env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "zai-glm-4.7"
    assert cerebras.env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "gpt-oss-120b"


def test_provider_schema_exposes_tui_and_config_metadata():
    provider = get_provider("zai")

    assert provider.tui["headline"] == "Z.ai Coding Plan"
    assert provider.settings_permissions_deny == [
        "mcp__4_5v_mcp__analyze_image",
        "mcp__milk_tea_server__claim_milk_tea_coupon",
        "mcp__web_reader__webReader",
    ]
    assert sorted(provider.mcp_servers) == ["web-reader", "web-search-prime", "zai-mcp-server", "zread"]


def test_provider_config_writer_merges_zai_mcp_and_denies(tmp_path):
    result = apply_provider_claude_config("zai", tmp_path, credential_value="zai-secret")

    settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    config = json.loads((tmp_path / ".claude.json").read_text(encoding="utf-8"))

    assert result.settings_changed is True
    assert result.claude_config_changed is True
    assert "mcp__web_reader__webReader" in settings["permissions"]["deny"]
    assert sorted(config["mcpServers"]) == ["web-reader", "web-search-prime", "zai-mcp-server", "zread"]
    assert config["mcpServers"]["web-reader"]["headers"] == {"Authorization": "Bearer zai-secret"}
    assert config["mcpServers"]["zai-mcp-server"]["env"]["Z_AI_API_KEY"] == "zai-secret"

    second = apply_provider_claude_config("zai", tmp_path, credential_value="zai-secret")
    assert second.settings_changed is False
    assert second.claude_config_changed is False


def test_provider_config_writer_preserves_existing_mcp_and_uses_placeholder(tmp_path):
    (tmp_path / ".claude.json").write_text(
        json.dumps({"mcpServers": {"user-mcp": {"command": "node", "args": ["server.js"]}}}),
        encoding="utf-8",
    )

    apply_provider_claude_config("zai", tmp_path)
    config = json.loads((tmp_path / ".claude.json").read_text(encoding="utf-8"))

    assert config["mcpServers"]["user-mcp"] == {"command": "node", "args": ["server.js"]}
    assert config["mcpServers"]["web-search-prime"]["headers"] == {
        "Authorization": f"Bearer {PLACEHOLDER_CREDENTIAL}"
    }


def test_provider_config_writer_adds_minimax_mcp(tmp_path):
    apply_provider_claude_config("minimax", tmp_path, credential_value="mini-secret")

    settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    config = json.loads((tmp_path / ".claude.json").read_text(encoding="utf-8"))

    assert settings["permissions"]["deny"] == ["WebSearch"]
    assert config["mcpServers"]["MiniMax"]["command"] == "uvx"
    assert config["mcpServers"]["MiniMax"]["env"]["MINIMAX_API_KEY"] == "mini-secret"
