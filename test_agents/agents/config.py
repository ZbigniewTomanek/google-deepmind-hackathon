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
        .mcp_server(name="neocortex", command="npx", args=["mcp-remote", mcp_url])
        .compaction(auto=True, prune=True)
        .build()
    )
