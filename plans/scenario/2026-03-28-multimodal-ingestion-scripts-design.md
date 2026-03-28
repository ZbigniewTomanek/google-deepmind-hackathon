# Multimodal Source Ingestion Scripts — Design Spec

**Date:** 2026-03-28
**Context:** Google DeepMind x AI Tinkerers Hackathon, Warsaw 2026
**Goal:** Demonstrate NeoCortex knowledge graph ingestion from multiple modalities — RSS feeds, audio, and video — using agent-composable ScriptTools.

## Overview

Four new ScriptTools in `test_agents/agent_scripts/` that parse multimodal sources into structured text. These are **pure parsers** — they return data for agents to decide what to `remember` in the knowledge graph. No side effects.

| Script | Purpose | External deps |
|--------|---------|---------------|
| `hackernews_rss.py` | Parse HN RSS feed into structured text items | `feedparser` |
| `transcribe_audio.py` | Download YouTube audio via `yt-dlp`, transcribe via Gemini with timestamps | `yt-dlp`, `google-genai` |
| `transcribe_video.py` | Download YouTube video via `yt-dlp`, transcribe via Gemini with timestamps + visual descriptions | `yt-dlp`, `google-genai` |
| `video_screenshot.py` | Extract a frame from a downloaded video at a given timestamp | `ffmpeg` (CLI) |

All scripts follow the existing `ScriptTool[Input, Output]` pattern from `open_agent_compiler.runtime`.

## Script Designs

### 1. `hackernews_rss.py`

**Input:**
- `feed_url: str = "https://hnrss.org/newest"` — RSS feed URL
- `max_items: int = 10` — how many items to return

**Output:**
- `items: list[dict]` — each with `title`, `link`, `published`, `summary`, `comments_url`
- `feed_title: str` — name of the feed
- `total_fetched: int`

**Implementation:**
- `feedparser.parse(feed_url)` fetches and parses the RSS
- Iterates over `feed.entries[:max_items]`
- HTML-strips summaries to plain text (stdlib `html.parser`, no extra dep)
- Returns structured list for the agent to selectively `remember`

### 2. `transcribe_audio.py`

**Input:**
- `youtube_url: str` — YouTube video URL
- `output_dir: str = ".agent_workspace"` — where to save the downloaded audio

**Output:**
- `transcript: list[dict]` — segments with `{timestamp: "MM:SS", end_timestamp: "MM:SS", text: str}`
- `full_text: str` — concatenated plain transcript
- `audio_path: str` — path to the downloaded audio file
- `duration_seconds: float` — total audio duration
- `title: str` — video title from yt-dlp metadata

**Implementation:**
1. `yt-dlp` downloads audio-only (`-x --audio-format mp3`) to `output_dir`
2. Upload audio file to Gemini via `google-genai` File API
3. Prompt Gemini: *"Transcribe this audio. Return a JSON array of segments, each with `timestamp` (MM:SS start), `end_timestamp` (MM:SS end), and `text`."*
4. Parse JSON response, concatenate into `full_text`

### 3. `transcribe_video.py`

**Input:**
- `youtube_url: str` — YouTube video URL
- `output_dir: str = ".agent_workspace"` — where to save the downloaded video

**Output:**
- `transcript: list[dict]` — segments with `{timestamp, end_timestamp, text, visual_description?}`
- `full_text: str` — concatenated transcript
- `video_path: str` — path to downloaded video (kept on disk for screenshot tool)
- `duration_seconds: float`
- `title: str`

**Implementation:**
1. `yt-dlp` downloads video (quality capped at 720p to keep file size manageable)
2. Upload video to Gemini File API
3. Prompt Gemini: *"Transcribe the speech in this video. Also note any significant visual content (slides, diagrams, code on screen) with timestamps. Return JSON array of segments with `timestamp`, `end_timestamp`, `text`, and optional `visual_description`."*
4. Parse response — `visual_description` field is what makes video different from audio-only

**Key difference from audio:** Video file stays on disk so `video_screenshot.py` can reference it. Transcript includes `visual_description` for segments where on-screen content matters (slides, diagrams, code).

### 4. `video_screenshot.py`

**Input:**
- `video_path: str` — path to a downloaded video file
- `timestamp: str` — timestamp in `MM:SS` or `HH:MM:SS` format
- `output_dir: str = ".agent_workspace"` — where to save the screenshot

**Output:**
- `screenshot_path: str` — absolute path to the extracted frame
- `timestamp: str` — the requested timestamp (echoed back)

**Implementation:**
1. Validates `video_path` exists
2. Runs `ffmpeg -ss {timestamp} -i {video_path} -frames:v 1 -q:v 2 {output_path}`
3. Output filename: `screenshot_{video_basename}_{timestamp}.jpg`
4. Returns the path for the agent to read/attach the image

## Demo Scenario

```
Agent receives task: "Research what's trending in AI this week"
  |
  +-- Agent calls hackernews_rss(max_items=5)
  |     \-- Gets 5 HN stories -> calls remember() for each interesting one
  |
  +-- Agent finds a relevant YouTube talk linked in HN
  |     +-- Calls transcribe_video(youtube_url=...)
  |     |     \-- Gets timestamped transcript with visual descriptions
  |     +-- Calls remember() for key segments
  |     \-- Calls video_screenshot(timestamp="12:34") for a diagram it found
  |
  \-- Knowledge graph now contains:
        - HN stories as episodes
        - Video transcript segments with timestamps
        - Extracted entities/relationships across all sources
```

This demonstrates three ingestion modalities (RSS text, audio, video) flowing into a unified knowledge graph, with agents orchestrating what gets remembered and how.

## Dependencies

- `feedparser` — RSS parsing
- `yt-dlp` — YouTube download (CLI tool, installable via pip or brew)
- `google-genai` — Gemini API client (already in project for embeddings)
- `ffmpeg` — frame extraction (CLI tool, must be installed on system)

## Integration Point

All scripts live in `test_agents/agent_scripts/` alongside existing tools (`google_search.py`, `youtube_search.py`, etc.) and follow the same `ScriptTool` pattern for consistency.
