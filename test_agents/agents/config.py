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
    research_orch_token = os.environ.get("NEOCORTEX_RESEARCH_ORCH_TOKEN", "research-orch-token")
    video_proc_token = os.environ.get("NEOCORTEX_VIDEO_PROC_TOKEN", "video-processor-token")
    audio_proc_token = os.environ.get("NEOCORTEX_AUDIO_PROC_TOKEN", "audio-processor-token")
    rss_proc_token = os.environ.get("NEOCORTEX_RSS_PROC_TOKEN", "rss-processor-token")
    chat_extractions_token = os.environ.get("NEOCORTEX_CHAT_EXTRACTIONS_TOKEN", "chat-extractions-token")

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
        .mcp_server(
            name="neocortex-research-orch",
            url=mcp_url,
            headers={"Authorization": f"Bearer {research_orch_token}"},
        )
        .mcp_server(
            name="neocortex-video-proc",
            url=mcp_url,
            headers={"Authorization": f"Bearer {video_proc_token}"},
        )
        .mcp_server(
            name="neocortex-audio-proc",
            url=mcp_url,
            headers={"Authorization": f"Bearer {audio_proc_token}"},
        )
        .mcp_server(
            name="neocortex-rss-proc",
            url=mcp_url,
            headers={"Authorization": f"Bearer {rss_proc_token}"},
        )
        .mcp_server(
            name="neocortex-chat-extractions",
            url=mcp_url,
            headers={"Authorization": f"Bearer {chat_extractions_token}"},
        )
        .compaction(auto=True, prune=True)
        .build()
    )
