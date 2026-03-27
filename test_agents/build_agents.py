"""Build test agents using OpenAgentCompiler and write to build/.

Agents:
- chat: Primary conversational agent that routes to subagents
- search-orchestrator: Routes search queries to YouTube or Google search
- youtube-search: Searches YouTube (mock)
- google-search: Searches Google/web (mock)
- task-subagent: Todo list management
- joke-subagent: Joke generation

All agents use z.ai provider with GLM-5 model.
NeoCortex MCP server is connected for memory operations.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from open_agent_compiler._types import (
    ActionDefinition,
    AgentPermissions,
    ModelConfig,
    ModelLimits,
    ModelOptions,
    ProviderConfig,
    ProviderOptions,
)
from open_agent_compiler.builders import (
    AgentBuilder,
    ConfigBuilder,
    SkillBuilder,
    SubagentBuilder,
    ToolBuilder,
    WorkflowStepBuilder,
)
from open_agent_compiler.compiler import compile_agent
from open_agent_compiler.predefined import subagent_todo_skill
from open_agent_compiler.writers import OpenCodeWriter

BUILD_DIR = Path(__file__).resolve().parent / "build"
SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"


# ── Config ──────────────────────────────────────────────────────────────────


def _build_config():
    """Shared config: z.ai provider with GLM-5 + NeoCortex MCP server."""
    api_key = os.environ.get("ZAI_API_KEY", "env:ZAI_API_KEY")
    base_url = os.environ.get("ZAI_BASE_URL", "https://api.z.ai/api/coding/paas/v4")
    mcp_url = os.environ.get("NEOCORTEX_MCP_URL", "http://localhost:8000")

    builder = (
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
        .mcp_server(
            name="neocortex",
            command="npx",
            args=["mcp-remote", mcp_url],
        )
        .compaction(auto=True, prune=True)
    )
    return builder.build()


# ── Tools ───────────────────────────────────────────────────────────────────


def _build_thought_transfer():
    """Inter-agent data passing tool."""
    return (
        ToolBuilder()
        .name("thought-transfer")
        .description("Read/write data between agents in the orchestration pipeline")
        .action(
            ActionDefinition(
                command_pattern="uv run scripts/thought_transfer.py *",
                description="Transfer data between agents",
                usage_example="uv run scripts/thought_transfer.py write customer_request",
            )
        )
        .example(
            "write",
            "Save data for another agent",
            "uv run scripts/thought_transfer.py write search_query",
        )
        .example(
            "read",
            "Read data from another agent",
            "uv run scripts/thought_transfer.py read search_results",
        )
        .example(
            "list",
            "List all stored data keys",
            "uv run scripts/thought_transfer.py list",
        )
        .build()
    )


def _build_joke_tool():
    return (
        ToolBuilder()
        .name("joke-tool")
        .description("Generate a joke on a given topic and style")
        .from_script(str(SCRIPTS_DIR / "joke_tool.py"))
        .build()
    )


def _build_youtube_search():
    return (
        ToolBuilder()
        .name("youtube-search-tool")
        .description("Search YouTube for videos matching a query")
        .from_script(str(SCRIPTS_DIR / "youtube_search.py"))
        .build()
    )


def _build_google_search():
    return (
        ToolBuilder()
        .name("google-search-tool")
        .description("Search the web for pages matching a query")
        .from_script(str(SCRIPTS_DIR / "google_search.py"))
        .build()
    )


def _build_task_manager():
    return (
        ToolBuilder()
        .name("task-manager")
        .description("Manage a todo list: add, list, complete, or delete tasks")
        .from_script(str(SCRIPTS_DIR / "task_manager.py"))
        .build()
    )


# ── Skills ──────────────────────────────────────────────────────────────────


def _build_search_skill(youtube_tool, google_tool):
    return (
        SkillBuilder()
        .name("web-search")
        .description("Search the web and YouTube for information")
        .instructions(
            "Use these tools to find information online.\n"
            "- Use youtube-search-tool for video content queries.\n"
            "- Use google-search-tool for general web queries.\n"
            "Present results clearly with titles, URLs, and descriptions."
        )
        .tool(youtube_tool)
        .tool(google_tool)
        .build()
    )


def _build_task_skill(task_tool):
    return (
        SkillBuilder()
        .name("task-management")
        .description("Create and manage todo lists")
        .instructions(
            "Use the task-manager tool to manage tasks.\n"
            "- action=add: Create a new task (requires title)\n"
            "- action=list: List all tasks\n"
            "- action=complete: Mark a task done (requires task_id)\n"
            "- action=delete: Remove a task (requires task_id)\n"
            "Always show the updated task list after changes."
        )
        .tool(task_tool)
        .build()
    )


# ── Joke Subagent ──────────────────────────────────────────────────────────


def build_joke_subagent(config):
    """Subagent that tells jokes."""
    joke_tool = _build_joke_tool()
    thought_transfer = _build_thought_transfer()

    step_1 = (
        WorkflowStepBuilder()
        .id("1")
        .name("Read Request")
        .todo("Read request", "Read the joke request from the orchestrator")
        .use_tool("thought-transfer", "read")
        .instructions("Read the joke_request from the chat agent via thought-transfer.")
        .mark_done("Read request")
        .build()
    )

    step_2 = (
        WorkflowStepBuilder()
        .id("2")
        .name("Generate Joke")
        .todo("Generate joke", "Create a joke using the joke tool")
        .use_tool("joke-tool")
        .instructions(
            "Use the joke-tool to generate a joke based on the request.\n"
            "Pick the topic from the request and choose an appropriate style.\n"
            "If no specific topic, use something relevant to the conversation."
        )
        .mark_done("Generate joke")
        .build()
    )

    step_3 = (
        WorkflowStepBuilder()
        .id("3")
        .name("Write Result")
        .todo("Write result", "Send the joke back to the orchestrator")
        .use_tool("thought-transfer", "write")
        .instructions("Write the generated joke via thought-transfer (key: joke_result) for the chat agent.")
        .mark_done("Write result")
        .build()
    )

    return (
        AgentBuilder()
        .name("joke-subagent")
        .description("Joke generation specialist — tells funny jokes on any topic")
        .mode("subagent")
        .config(config)
        .tool(joke_tool)
        .tool(thought_transfer)
        .skill(
            subagent_todo_skill(),
            instruction="Use for mandatory progress tracking in every run",
        )
        .preamble(
            "# Joke Subagent\n\n"
            "You are a comedy specialist. Your job is to generate funny, relevant jokes.\n"
            "Read the request from thought-transfer, generate a joke with the joke-tool,\n"
            "and write the result back.\n\n"
            "Be creative and tailor the humor to the requested topic."
        )
        .workflow_step(step_1)
        .workflow_step(step_2)
        .workflow_step(step_3)
        .temperature(0.7)
        .build()
    )


# ── Search Orchestrator ────────────────────────────────────────────────────


def build_search_orchestrator(config):
    """Subagent that handles search queries using YouTube and Google tools directly."""
    thought_transfer = _build_thought_transfer()
    yt_tool = _build_youtube_search()
    google_tool = _build_google_search()
    search_skill = _build_search_skill(yt_tool, google_tool)

    step_1 = (
        WorkflowStepBuilder()
        .id("1")
        .name("Read Search Request")
        .todo("Read request", "Read the search request from the chat agent")
        .use_tool("thought-transfer", "read")
        .instructions("Read the search_request from the chat agent via thought-transfer.")
        .mark_done("Read request")
        .build()
    )

    step_2 = (
        WorkflowStepBuilder()
        .id("2")
        .name("Evaluate Query Type")
        .todo("Evaluate query", "Determine if this is a video or web search")
        .evaluate(
            "search_type",
            "What type of search is most appropriate for this query?",
            "video",
            "web",
            "both",
        )
        .instructions(
            "Analyze the search request to determine the best search strategy:\n"
            "- video: User wants video content (tutorials, demos, talks)\n"
            "- web: User wants articles, docs, or general information\n"
            "- both: User would benefit from both video and web results"
        )
        .route("search_type", "video", goto="3")
        .route("search_type", "web", goto="4")
        .route("search_type", "both", goto="3")
        .mark_done("Evaluate query")
        .build()
    )

    step_3 = (
        WorkflowStepBuilder()
        .id("3")
        .name("YouTube Search")
        .todo("YouTube search", "Search YouTube for video results")
        .use_tool("youtube-search-tool")
        .instructions(
            "Use the youtube-search-tool to search for videos matching the query.\n"
            "Use max_results=5 for a good balance of results."
        )
        .mark_done("YouTube search")
        .build()
    )

    step_4 = (
        WorkflowStepBuilder()
        .id("4")
        .name("Google Search")
        .todo("Google search", "Search the web for results")
        .use_tool("google-search-tool")
        .instructions(
            "Use the google-search-tool to search the web for relevant pages.\n"
            "Use max_results=5 for a good balance of results."
        )
        .mark_done("Google search")
        .build()
    )

    step_5 = (
        WorkflowStepBuilder()
        .id("5")
        .name("Write Aggregated Results")
        .todo("Write results", "Send aggregated search results back to chat agent")
        .use_tool("thought-transfer", "write")
        .instructions(
            "Compile all search results into a clear, organized response.\n"
            "Write the aggregated results via thought-transfer (key: search_response)\n"
            "for the chat agent to deliver to the user."
        )
        .mark_done("Write results")
        .build()
    )

    return (
        AgentBuilder()
        .name("search-orchestrator")
        .description("Search orchestrator — searches YouTube and Google directly")
        .mode("subagent")
        .config(config)
        .tool(thought_transfer)
        .tool(yt_tool)
        .tool(google_tool)
        .skill(
            search_skill,
            instruction="Use for all search operations",
        )
        .skill(
            subagent_todo_skill(),
            instruction="Use for mandatory progress tracking in every run",
        )
        .preamble(
            "# Search Orchestrator\n\n"
            "You handle search requests using YouTube and Google search tools:\n"
            "- **youtube-search-tool**: For video content queries\n"
            "- **google-search-tool**: For web/article queries\n\n"
            "Analyze the query, determine the best search strategy, execute the search,\n"
            "and write aggregated results back via thought-transfer."
        )
        .workflow_step(step_1)
        .workflow_step(step_2)
        .workflow_step(step_3)
        .workflow_step(step_4)
        .workflow_step(step_5)
        .temperature(0.3)
        .build()
    )


# ── Task Subagent ──────────────────────────────────────────────────────────


def build_task_subagent(config):
    """Subagent that manages todo lists."""
    task_tool = _build_task_manager()
    thought_transfer = _build_thought_transfer()
    task_skill = _build_task_skill(task_tool)

    step_1 = (
        WorkflowStepBuilder()
        .id("1")
        .name("Read Request")
        .todo("Read request", "Read the task request from the chat agent")
        .use_tool("thought-transfer", "read")
        .instructions("Read the task_request from the chat agent via thought-transfer.")
        .mark_done("Read request")
        .build()
    )

    step_2 = (
        WorkflowStepBuilder()
        .id("2")
        .name("Execute Task Operation")
        .todo("Execute operation", "Perform the requested task management action")
        .use_tool("task-manager")
        .instructions(
            "Based on the request, execute the appropriate task-manager action:\n"
            "- To add a task: use action=add with the title\n"
            "- To list tasks: use action=list\n"
            "- To complete a task: use action=complete with the task_id\n"
            "- To delete a task: use action=delete with the task_id"
        )
        .mark_done("Execute operation")
        .build()
    )

    step_3 = (
        WorkflowStepBuilder()
        .id("3")
        .name("Write Result")
        .todo("Write result", "Send task results back to chat agent")
        .use_tool("thought-transfer", "write")
        .instructions("Write the task operation result via thought-transfer (key: task_result) for the chat agent.")
        .mark_done("Write result")
        .build()
    )

    return (
        AgentBuilder()
        .name("task-subagent")
        .description("Todo list management specialist — creates and manages task lists")
        .mode("subagent")
        .config(config)
        .tool(task_tool)
        .tool(thought_transfer)
        .skill(
            task_skill,
            instruction="Use for all task management operations",
        )
        .skill(
            subagent_todo_skill(),
            instruction="Use for mandatory progress tracking in every run",
        )
        .preamble(
            "# Task Subagent\n\n"
            "You manage todo lists for users. Read requests from thought-transfer,\n"
            "execute task operations, and write results back.\n"
            "Always show the current task list after any modification."
        )
        .workflow_step(step_1)
        .workflow_step(step_2)
        .workflow_step(step_3)
        .temperature(0.2)
        .build()
    )


# ── Chat Agent (Primary) ──────────────────────────────────────────────────


def build_chat(config):
    """Primary chat agent that routes to subagents."""
    thought_transfer = _build_thought_transfer()

    search_ref = (
        SubagentBuilder()
        .name("search-orchestrator")
        .description("Search orchestrator — routes to YouTube and Google search agents")
        .notes(
            "Handles all search queries: web, YouTube, mixed.\n"
            "Write search_request via thought-transfer before invoking."
        )
        .build()
    )

    task_ref = (
        SubagentBuilder()
        .name("task-subagent")
        .description("Todo list management specialist")
        .notes(
            "Handles todo list operations: add, list, complete, delete.\n"
            "Write task_request via thought-transfer before invoking."
        )
        .build()
    )

    joke_ref = (
        SubagentBuilder()
        .name("joke-subagent")
        .description("Joke generation specialist")
        .notes(
            "Tells funny jokes on any topic.\n"
            "Write joke_request via thought-transfer before invoking."
        )
        .build()
    )

    step_1 = (
        WorkflowStepBuilder()
        .id("1")
        .name("Analyze User Intent")
        .todo("Analyze intent", "Determine what the user wants")
        .evaluate(
            "intent",
            "What is the user trying to do?",
            "search",
            "task",
            "joke",
            "general",
        )
        .instructions(
            "Read the user's message and determine their intent:\n"
            "- search: Looking for information, videos, articles (e.g. 'search for...', 'find...')\n"
            "- task: Managing todo lists (e.g. 'add task', 'create todo', 'my tasks')\n"
            "- joke: Wants a joke or humor (e.g. 'tell me a joke', 'make me laugh')\n"
            "- general: General conversation, questions, or anything else\n\n"
            "If the message contains <CONVERSATION_HISTORY> tags, use that context to\n"
            "better understand the user's current request."
        )
        .route("intent", "search", goto="2")
        .route("intent", "task", goto="3")
        .route("intent", "joke", goto="4")
        .route("intent", "general", goto="5")
        .mark_done("Analyze intent")
        .build()
    )

    step_2 = (
        WorkflowStepBuilder()
        .id("2")
        .name("Search Request")
        .todo("Run search", "Delegate to search orchestrator")
        .gate("intent", "search")
        .use_tool("thought-transfer", "write")
        .subagent("search-orchestrator")
        .instructions(
            "1. Write the user's search query via thought-transfer (key: search_request)\n"
            "2. Invoke the search-orchestrator subagent via Task tool\n"
            "3. Read results from thought-transfer (key: search_response) after subagent completes"
        )
        .mark_done("Run search")
        .build()
    )

    step_3 = (
        WorkflowStepBuilder()
        .id("3")
        .name("Task Management")
        .todo("Run task manager", "Delegate to task subagent")
        .gate("intent", "task")
        .use_tool("thought-transfer", "write")
        .subagent("task-subagent")
        .instructions(
            "1. Write the user's task request via thought-transfer (key: task_request)\n"
            "2. Invoke the task-subagent via Task tool\n"
            "3. Read results from thought-transfer (key: task_result) after subagent completes"
        )
        .mark_done("Run task manager")
        .build()
    )

    step_4 = (
        WorkflowStepBuilder()
        .id("4")
        .name("Tell Joke")
        .todo("Run joke agent", "Delegate to joke subagent")
        .gate("intent", "joke")
        .use_tool("thought-transfer", "write")
        .subagent("joke-subagent")
        .instructions(
            "1. Write the joke request via thought-transfer (key: joke_request)\n"
            "   Include the topic if the user specified one.\n"
            "2. Invoke the joke-subagent via Task tool\n"
            "3. Read results from thought-transfer (key: joke_result) after subagent completes"
        )
        .mark_done("Run joke agent")
        .build()
    )

    step_5 = (
        WorkflowStepBuilder()
        .id("5")
        .name("General Response")
        .todo("Answer directly", "Respond to general conversation")
        .gate("intent", "general")
        .instructions(
            "Answer the user's question or message directly.\n"
            "Use the NeoCortex MCP tools (remember, recall, discover) if relevant:\n"
            "- remember: Store important facts the user tells you\n"
            "- recall: Retrieve previously stored memories\n"
            "- discover: Explore the knowledge graph for connections\n\n"
            "Be helpful, concise, and friendly."
        )
        .mark_done("Answer directly")
        .build()
    )

    step_6 = (
        WorkflowStepBuilder()
        .id("6")
        .name("Deliver Response")
        .todo("Deliver response", "Format and deliver the final response")
        .use_tool("thought-transfer", "read")
        .instructions(
            "If a subagent was invoked, read its results from thought-transfer.\n"
            "Format a clear, friendly response for the user.\n"
            "Include the subagent's output and add any helpful context.\n"
            "Suggest follow-up actions when appropriate."
        )
        .mark_done("Deliver response")
        .build()
    )

    return (
        AgentBuilder()
        .name("chat")
        .description("Primary chat agent — routes to search, task, and joke subagents")
        .mode("primary")
        .config(config)
        .tool(thought_transfer)
        .subagent(search_ref)
        .subagent(task_ref)
        .subagent(joke_ref)
        .preamble(
            "# Chat Agent\n\n"
            "You are the primary conversational agent for the NeoCortex memory test suite.\n"
            "You help users by routing their requests to specialist subagents:\n"
            "- **search-orchestrator**: For searching YouTube and the web\n"
            "- **task-subagent**: For managing todo lists\n"
            "- **joke-subagent**: For telling jokes\n\n"
            "For general questions, you answer directly.\n\n"
            "## Context Handling\n"
            "If the user's message contains a `<CONVERSATION_HISTORY>` block, treat those\n"
            "as prior conversation turns. Use them as context for your response. The actual\n"
            "request follows after the history block.\n\n"
            "## Memory Integration\n"
            "You are connected to the NeoCortex MCP server. Use its tools when relevant:\n"
            "- **remember**: Store facts, preferences, or important information\n"
            "- **recall**: Retrieve previously stored memories\n"
            "- **discover**: Explore connections in the knowledge graph\n\n"
            "Always be helpful, friendly, and proactive."
        )
        .workflow_step(step_1)
        .workflow_step(step_2)
        .workflow_step(step_3)
        .workflow_step(step_4)
        .workflow_step(step_5)
        .workflow_step(step_6)
        .postamble(
            "## Tone Guidelines\n\n"
            "- Friendly and conversational\n"
            "- Concise but informative\n"
            "- Suggest follow-up actions\n"
            "- Use the user's language and tone"
        )
        .permissions(AgentPermissions(doom_loop="deny"))
        .temperature(0.4)
        .steps(100)
        .color("#4A90D9")
        .build()
    )


# ── Main ────────────────────────────────────────────────────────────────────


def compile_and_write() -> Path:
    """Compile all agents and write to build directory. Returns build path."""
    config = _build_config()

    # Build agent definitions
    joke_def = build_joke_subagent(config)
    search_orch_def = build_search_orchestrator(config)
    task_def = build_task_subagent(config)
    chat_def = build_chat(config)

    # Compile
    joke_compiled = compile_agent(joke_def, target="opencode")
    search_orch_compiled = compile_agent(search_orch_def, target="opencode")
    task_compiled = compile_agent(task_def, target="opencode")
    chat_compiled = compile_agent(chat_def, target="opencode")

    # Write all to same build directory
    writer = OpenCodeWriter(output_dir=BUILD_DIR, scripts_dir=SCRIPTS_DIR)
    writer.write(chat_compiled)
    writer.write(search_orch_compiled)
    writer.write(task_compiled)
    writer.write(joke_compiled)

    return BUILD_DIR


def main() -> None:
    build_dir = compile_and_write()
    print(f"Agents compiled and written to {build_dir}")
    print()
    print("Agents built:")
    print("  - chat (primary)")
    print("  - search-orchestrator (subagent) — uses youtube + google search tools directly")
    print("  - task-subagent (subagent)")
    print("  - joke-subagent (subagent)")
    print()
    print("Provider: z.ai / GLM-5")
    print("MCP: NeoCortex (memory)")


if __name__ == "__main__":
    main()
