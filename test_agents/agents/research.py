"""Research agent — multimodal ingestion with NeoCortex memory."""

from __future__ import annotations

from open_agent_compiler._types import AgentPermissions, ToolPermissions
from open_agent_compiler.builders import AgentBuilder, WorkflowStepBuilder

from agents.tools import (
    build_google_search,
    build_hackernews_rss,
    build_transcribe_audio,
    build_transcribe_video,
    build_video_screenshot,
)


def build_research_agent(config):
    hn_tool = build_hackernews_rss()
    audio_tool = build_transcribe_audio()
    video_tool = build_transcribe_video()
    screenshot_tool = build_video_screenshot()
    google_tool = build_google_search()

    step_1 = (
        WorkflowStepBuilder()
        .id("1")
        .name("Recall Context")
        .todo("Recall context", "Check memory for relevant prior knowledge")
        .instructions(
            "Run `neocortex-research` `recall` with the user's research topic to check for prior memories.\n"
            "Run `discover` to understand what knowledge is already in the graph.\n"
            "Note any relevant recalled facts to avoid duplicate ingestion."
        )
        .mark_done("Recall context")
        .build()
    )

    step_2 = (
        WorkflowStepBuilder()
        .id("2")
        .name("Gather Sources")
        .todo("Gather sources", "Collect data from RSS, audio, video, or web")
        .use_tool("hackernews-rss")
        .use_tool("transcribe-audio")
        .use_tool("transcribe-video")
        .use_tool("video-screenshot")
        .use_tool("google-search-tool")
        .instructions(
            "Based on the user's request, gather information from the appropriate sources:\n\n"
            "- **hackernews-rss**: Parse HN or other RSS feeds for trending stories and discussions.\n"
            "- **transcribe-audio**: Download and transcribe YouTube audio with timestamps.\n"
            "- **transcribe-video**: Download and transcribe YouTube video with timestamps and visual descriptions.\n"
            "  Use this when the video contains slides, diagrams, or code on screen.\n"
            "- **video-screenshot**: Extract a frame from a downloaded video at a specific timestamp.\n"
            "  Use this after transcribe-video when a visual_description mentions something worth capturing.\n"
            "- **google-search-tool**: Search the web for additional context.\n\n"
            "You may use multiple tools in sequence. For example:\n"
            "1. Parse HN RSS to find trending topics\n"
            "2. Find a relevant YouTube video linked in a story\n"
            "3. Transcribe the video\n"
            "4. Screenshot interesting visual moments"
        )
        .mark_done("Gather sources")
        .build()
    )

    step_3 = (
        WorkflowStepBuilder()
        .id("3")
        .name("Remember Key Findings")
        .todo("Remember findings", "Store important findings in NeoCortex memory")
        .instructions(
            "Review all gathered data and store important findings using `neocortex-research` `remember`.\n\n"
            "For each source, call `remember` with:\n"
            "- The key content as `text`\n"
            "- Source metadata as `context` (e.g., 'HackerNews story: {title}', "
            "'YouTube transcript segment at {timestamp}', 'Video screenshot at {timestamp}')\n\n"
            "Be selective — store facts, insights, and notable quotes, not everything.\n"
            "For video transcripts, store segments that contain substantive content, not filler."
        )
        .mark_done("Remember findings")
        .build()
    )

    step_4 = (
        WorkflowStepBuilder()
        .id("4")
        .name("Summarize")
        .todo("Summarize", "Present findings to the user")
        .instructions(
            "Summarize what was ingested and stored in the knowledge graph.\n"
            "Include:\n"
            "- Number of sources processed (RSS items, audio/video transcripts)\n"
            "- Key findings and themes\n"
            "- What entities and relationships were extracted\n"
            "- Any interesting cross-source connections discovered"
        )
        .mark_done("Summarize")
        .build()
    )

    return (
        AgentBuilder()
        .name("research-agent")
        .description("Multimodal research agent — ingests RSS, audio, video into NeoCortex knowledge graph")
        .mode("primary")
        .config(config)
        .tool(hn_tool)
        .tool(audio_tool)
        .tool(video_tool)
        .tool(screenshot_tool)
        .tool(google_tool)
        .tool_permissions(ToolPermissions(mcp=True))
        .preamble(
            "# Research Agent\n\n"
            "You are a multimodal research agent that gathers information from diverse sources\n"
            "and stores structured knowledge in NeoCortex.\n\n"
            "## Your capabilities:\n"
            "- **RSS feeds**: Parse HackerNews and other RSS feeds for trending stories\n"
            "- **Audio transcription**: Download and transcribe YouTube audio with timestamps via Gemini\n"
            "- **Video transcription**: Transcribe YouTube video with visual descriptions via Gemini\n"
            "- **Video screenshots**: Extract frames at specific timestamps from downloaded videos\n"
            "- **Web search**: Search Google for additional context\n"
            "- **Memory**: Store and recall knowledge via NeoCortex MCP (neocortex-research)\n\n"
            "## Workflow:\n"
            "1. Recall existing knowledge on the topic\n"
            "2. Gather data from the requested sources\n"
            "3. Store key findings in NeoCortex memory with proper context\n"
            "4. Summarize what was learned\n\n"
            "Connected to NeoCortex MCP (neocortex-research) for memory (remember/recall/discover)."
        )
        .workflow_step(step_1)
        .workflow_step(step_2)
        .workflow_step(step_3)
        .workflow_step(step_4)
        .permissions(AgentPermissions(
            extra=(("neocortex-research*", "allow"),),
        ))
        .temperature(0.3)
        .steps(100)
        .color("#00CFD5")
        .build()
    )
