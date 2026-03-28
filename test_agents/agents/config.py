"""Shared LLM provider and MCP config for all agents."""

from __future__ import annotations

import os

from open_agent_compiler._types import (
    ModelConfig,
    ModelLimits,
    ModelOptions,
    ProviderConfig,
    ProviderOptions,
)
from open_agent_compiler.builders import ConfigBuilder


def build_config():
    api_key = os.environ.get("ZAI_API_KEY", "env:ZAI_API_KEY")
    base_url = os.environ.get("ZAI_BASE_URL", "https://api.z.ai/api/coding/paas/v4")
    mcp_url = os.environ.get("NEOCORTEX_MCP_URL", "http://localhost:8000")
    chat_token = os.environ.get("NEOCORTEX_CHAT_TOKEN", "chat-agent-token")
    joke_token = os.environ.get("NEOCORTEX_JOKE_TOKEN", "joke-agent-token")

    return (
        ConfigBuilder()
        .provider(
            ProviderConfig(
                name="zai-coding-plan",
                options=ProviderOptions(
                    api_key=api_key,
                    base_url=base_url,
                    timeout=600000,
                    max_retries=2,
                ),
                models=(
                    ModelConfig(
                        name="glm-5",
                        id="glm-5",
                        limits=ModelLimits(context=131072, output=16384),
                        options=ModelOptions(temperature=0.3, top_p=0.9),
                    ),
                ),
            )
        )
        .default_model("zai-coding-plan/glm-5")
        # Original single MCP for existing agents (no auth)
        .mcp_server(name="neocortex", url=mcp_url)
        # Per-agent MCP with auth tokens (remote + headers)
        .mcp_server(
            name="neocortex-chat",
            url=mcp_url,
            headers={"Authorization": f"Bearer {chat_token}"},
        )
        .mcp_server(
            name="neocortex-joke",
            url=mcp_url,
            headers={"Authorization": f"Bearer {joke_token}"},
        )
        .compaction(auto=True, prune=True)
        .build()
    )
