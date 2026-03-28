"""Video processor subagent — transcribes and stores to shared research graph."""

from __future__ import annotations

from open_agent_compiler._types import AgentPermissions
from open_agent_compiler.builders import AgentBuilder, WorkflowStepBuilder

from agents.tools import build_list_input_files, build_transcribe_local_video, build_video_screenshot


def build_video_processor(config):
    list_files_tool = build_list_input_files()
    video_tool = build_transcribe_local_video()
    screenshot_tool = build_video_screenshot()

    step_1 = (
        WorkflowStepBuilder()
        .id("1")
        .name("Process Video")
        .todo("Process video", "Transcribe local video file and extract key screenshots")
        .use_tool("transcribe-local-video")
        .use_tool("video-screenshot")
        .instructions(
            "Transcribe the local video file using transcribe-local-video.\n"
            "Review the transcript for key moments — slides, diagrams, code, or important visuals.\n"
            "Use video-screenshot to extract frames at those timestamps.\n"
            "Note the most important findings, quotes, and visual content."
        )
        .mark_done("Process video")
        .build()
    )

    step_2 = (
        WorkflowStepBuilder()
        .id("2")
        .name("Share Findings")
        .todo("Share findings", "Store transcript and visual findings to shared research graph")
        .instructions(
            "Store key findings in the shared research graph using `neocortex-video-proc` `remember`.\n\n"
            "For each important segment, call `remember` with:\n"
            "- `target_graph`: `ncx_shared__research`\n"
            "- `text`: the key content (transcript segment, visual description)\n"
            "- `context`: source metadata (e.g., 'Video transcript: {title} at {timestamp}', "
            "'Video screenshot: {title} at {timestamp}')\n\n"
            "Be selective — store substantive content, insights, and notable quotes, not filler."
        )
        .mark_done("Share findings")
        .build()
    )

    return (
        AgentBuilder()
        .name("video-processor")
        .description("Transcribes local video files and stores findings in shared research graph")
        .mode("subagent")
        .config(config)
        .tool(list_files_tool)
        .tool(video_tool)
        .tool(screenshot_tool)
        .preamble(
            "# Video Processor\n\n"
            "You are a video processing subagent that transcribes local video files\n"
            "and stores structured findings in a shared research knowledge graph.\n\n"
            "## Your capabilities:\n"
            "- **Video transcription**: Transcribe local video files via Gemini with timestamps\n"
            "- **Video screenshots**: Extract frames at specific timestamps\n"
            "- **Shared memory**: Store findings via NeoCortex MCP (neocortex-video-proc)\n\n"
            "## Workflow:\n"
            "1. Transcribe the video and extract screenshots at key moments\n"
            "2. Store transcript segments and visual findings to the shared research graph\n\n"
            "All findings go to `ncx_shared__research` via `remember(target_graph=...)`.\n"
            "Connected to NeoCortex MCP (neocortex-video-proc) for shared graph access."
        )
        .workflow_step(step_1)
        .workflow_step(step_2)
        .permissions(AgentPermissions(
            extra=(("neocortex-video-proc*", "allow"),),
        ))
        .temperature(0.3)
        .build()
    )
