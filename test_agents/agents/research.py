"""Research orchestrator — routes input files to modality-specific subagents."""

from __future__ import annotations

from open_agent_compiler._types import AgentPermissions, ToolPermissions
from open_agent_compiler.builders import AgentBuilder, SubagentBuilder, WorkflowStepBuilder

from agents.tools import build_list_input_files


def build_research_orchestrator(config):
    list_files_tool = build_list_input_files()

    video_ref = SubagentBuilder().name("video-processor").description("Transcribes local video files and stores findings in shared research graph").build()
    audio_ref = SubagentBuilder().name("audio-processor").description("Transcribes local audio files and stores findings in shared research graph").build()
    rss_ref = SubagentBuilder().name("rss-processor").description("Parses local RSS feeds and stores findings in shared research graph").build()

    step_1 = (
        WorkflowStepBuilder()
        .id("1")
        .name("Recall Context")
        .todo("Recall context", "Check memory for relevant prior knowledge")
        .instructions(
            "Run `neocortex-research-orch` `recall` with the user's research topic to check for prior memories.\n"
            "Run `discover` to understand what knowledge is already in the graph.\n"
            "Note any relevant recalled facts to avoid duplicate ingestion."
        )
        .mark_done("Recall context")
        .build()
    )

    step_2 = (
        WorkflowStepBuilder()
        .id("2")
        .name("Scan Input")
        .todo("Scan input", "List files in /app/input to determine what to process")
        .use_tool("list-input-files")
        .instructions(
            "Use list-input-files to see what files are available in /app/input.\n"
            "Note each file's extension and size to determine the appropriate processing modality."
        )
        .mark_done("Scan input")
        .build()
    )

    step_3 = (
        WorkflowStepBuilder()
        .id("3")
        .name("Classify & Route")
        .todo("Classify and route", "Delegate files to appropriate subagents by type")
        .subagent("video-processor")
        .subagent("audio-processor")
        .subagent("rss-processor")
        .instructions(
            "Classify files from the scan by extension and delegate to the appropriate subagent:\n\n"
            "- **Video** (`.mp4`, `.webm`, `.mkv`) → delegate to `video-processor`\n"
            "- **Audio** (`.mp3`, `.wav`, `.opus`, `.m4a`) → delegate to `audio-processor`\n"
            "- **RSS/Feeds** (`.rss`, `.xml`, `.atom`) → delegate to `rss-processor`\n\n"
            "If multiple modalities are present, delegate to each appropriate subagent in turn.\n"
            "Pass the full file path to each subagent so it knows which file to process.\n"
            "If no files are found, skip to the summary step."
        )
        .mark_done("Classify and route")
        .build()
    )

    step_4 = (
        WorkflowStepBuilder()
        .id("4")
        .name("Summarize")
        .todo("Summarize", "Collect results and present summary")
        .instructions(
            "Summarize what was processed and stored in the shared research graph.\n"
            "Include:\n"
            "- Number and types of files processed\n"
            "- Key findings and themes from each modality\n"
            "- What entities and relationships were extracted\n"
            "- Any interesting cross-source connections discovered\n\n"
            "If no files were found, report that the input directory was empty."
        )
        .mark_done("Summarize")
        .build()
    )

    return (
        AgentBuilder()
        .name("research-orchestrator")
        .description("Routes input files to modality-specific subagents for processing into shared research graph")
        .mode("primary")
        .config(config)
        .tool(list_files_tool)
        .subagent(video_ref)
        .subagent(audio_ref)
        .subagent(rss_ref)
        .tool_permissions(ToolPermissions(mcp=True))
        .preamble(
            "# Research Orchestrator\n\n"
            "You are a research orchestrator that scans an input directory for media files\n"
            "and delegates processing to specialized subagents.\n\n"
            "## Your capabilities:\n"
            "- **File scanning**: List files in /app/input with types and sizes\n"
            "- **Video processing**: Delegate `.mp4`, `.webm`, `.mkv` to video-processor\n"
            "- **Audio processing**: Delegate `.mp3`, `.wav`, `.opus`, `.m4a` to audio-processor\n"
            "- **RSS processing**: Delegate `.rss`, `.xml`, `.atom` to rss-processor\n"
            "- **Memory**: Recall and discover prior knowledge via NeoCortex MCP (neocortex-research-orch)\n\n"
            "## Workflow:\n"
            "1. Recall existing knowledge on the topic\n"
            "2. Scan input directory for files\n"
            "3. Classify files by modality and route to appropriate subagents\n"
            "4. Summarize what was processed and stored\n\n"
            "Subagents write findings directly to the shared graph `ncx_shared__research`.\n"
            "Connected to NeoCortex MCP (neocortex-research-orch) for memory (remember/recall/discover)."
        )
        .workflow_step(step_1)
        .workflow_step(step_2)
        .workflow_step(step_3)
        .workflow_step(step_4)
        .permissions(AgentPermissions(
            extra=(("neocortex-research-orch*", "allow"),),
        ))
        .temperature(0.3)
        .steps(100)
        .color("#00CFD5")
        .build()
    )
