"""Tool definitions shared across agents."""

from __future__ import annotations

from pathlib import Path

from open_agent_compiler.builders import ToolBuilder

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "agent_scripts"


def build_joke_tool():
    return (
        ToolBuilder()
        .name("joke-tool")
        .description("Generate a joke on a given topic and style")
        .from_script(str(SCRIPTS_DIR / "joke_tool.py"))
        .build()
    )


def build_youtube_search():
    return (
        ToolBuilder()
        .name("youtube-search-tool")
        .description("Search YouTube for videos matching a query")
        .from_script(str(SCRIPTS_DIR / "youtube_search.py"))
        .build()
    )


def build_google_search():
    return (
        ToolBuilder()
        .name("google-search-tool")
        .description("Search the web for pages matching a query")
        .from_script(str(SCRIPTS_DIR / "google_search.py"))
        .build()
    )


def build_task_manager():
    return (
        ToolBuilder()
        .name("task-manager")
        .description("Manage a todo list: add, list, complete, or delete tasks")
        .from_script(str(SCRIPTS_DIR / "task_manager.py"))
        .build()
    )


def build_hackernews_rss():
    return (
        ToolBuilder()
        .name("hackernews-rss")
        .description("Parse an RSS feed (defaults to HackerNews) and return structured items")
        .from_script(str(SCRIPTS_DIR / "hackernews_rss.py"))
        .build()
    )


def build_transcribe_audio():
    return (
        ToolBuilder()
        .name("transcribe-audio")
        .description("Download YouTube audio and transcribe it via Gemini with timestamps")
        .from_script(str(SCRIPTS_DIR / "transcribe_audio.py"))
        .build()
    )


def build_transcribe_video():
    return (
        ToolBuilder()
        .name("transcribe-video")
        .description("Download YouTube video and transcribe via Gemini with timestamps and visual descriptions")
        .from_script(str(SCRIPTS_DIR / "transcribe_video.py"))
        .build()
    )


def build_video_screenshot():
    return (
        ToolBuilder()
        .name("video-screenshot")
        .description("Extract a frame from a video at a specific timestamp")
        .from_script(str(SCRIPTS_DIR / "video_screenshot.py"))
        .build()
    )


def build_list_input_files():
    return (
        ToolBuilder()
        .name("list-input-files")
        .description("List files in a directory with file types and sizes")
        .from_script(str(SCRIPTS_DIR / "list_input_files.py"))
        .build()
    )


def build_transcribe_local_video():
    return (
        ToolBuilder()
        .name("transcribe-local-video")
        .description("Transcribe a local video file via Gemini with timestamps and visual descriptions")
        .from_script(str(SCRIPTS_DIR / "transcribe_local_video.py"))
        .build()
    )


def build_transcribe_local_audio():
    return (
        ToolBuilder()
        .name("transcribe-local-audio")
        .description("Transcribe a local audio file via Gemini with timestamps")
        .from_script(str(SCRIPTS_DIR / "transcribe_local_audio.py"))
        .build()
    )


def build_parse_local_rss():
    return (
        ToolBuilder()
        .name("parse-local-rss")
        .description("Parse a local RSS/Atom feed file and return structured items")
        .from_script(str(SCRIPTS_DIR / "parse_local_rss.py"))
        .build()
    )
