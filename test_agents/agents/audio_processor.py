"""Audio processor subagent — transcribes and stores to shared research graph."""

from __future__ import annotations

from open_agent_compiler._types import AgentPermissions
from open_agent_compiler.builders import AgentBuilder, WorkflowStepBuilder

from agents.tools import build_transcribe_local_audio


def build_audio_processor(config):
    audio_tool = build_transcribe_local_audio()

    step_1 = (
        WorkflowStepBuilder()
        .id("1")
        .name("Process Audio")
        .todo("Process audio", "Transcribe local audio file")
        .use_tool("transcribe-local-audio")
        .instructions(
            "Transcribe the local audio file using transcribe-local-audio.\n"
            "Review the transcript and identify key topics, insights, and notable quotes.\n"
            "Note timestamps for the most important segments."
        )
        .mark_done("Process audio")
        .build()
    )

    step_2 = (
        WorkflowStepBuilder()
        .id("2")
        .name("Share Findings")
        .todo("Share findings", "Store transcript and key findings to shared research graph")
        .instructions(
            "Store key findings in the shared research graph using `neocortex-audio-proc` `remember`.\n\n"
            "For each important segment, call `remember` with:\n"
            "- `target_graph`: `ncx_shared__research`\n"
            "- `text`: the key content (transcript segment, insight, quote)\n"
            "- `context`: source metadata (e.g., 'Audio transcript: {title} at {timestamp}')\n\n"
            "Be selective — store substantive content, insights, and notable quotes, not filler."
        )
        .mark_done("Share findings")
        .build()
    )

    return (
        AgentBuilder()
        .name("audio-processor")
        .description("Transcribes local audio files and stores findings in shared research graph")
        .mode("subagent")
        .config(config)
        .tool(audio_tool)
        .preamble(
            "# Audio Processor\n\n"
            "You are an audio processing subagent that transcribes local audio files\n"
            "and stores structured findings in a shared research knowledge graph.\n\n"
            "## Your capabilities:\n"
            "- **Audio transcription**: Transcribe local audio files via Gemini with timestamps\n"
            "- **Shared memory**: Store findings via NeoCortex MCP (neocortex-audio-proc)\n\n"
            "## Workflow:\n"
            "1. Transcribe the audio file and identify key content\n"
            "2. Store transcript segments and key findings to the shared research graph\n\n"
            "All findings go to `ncx_shared__research` via `remember(target_graph=...)`.\n"
            "Connected to NeoCortex MCP (neocortex-audio-proc) for shared graph access."
        )
        .workflow_step(step_1)
        .workflow_step(step_2)
        .permissions(AgentPermissions(
            extra=(("neocortex-audio-proc*", "allow"),),
        ))
        .temperature(0.3)
        .build()
    )
