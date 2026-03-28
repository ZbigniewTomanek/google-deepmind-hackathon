#!/usr/bin/env python3
"""YouTube video transcription tool — downloads video and transcribes via Gemini API with visual descriptions."""

import json
import os
import subprocess
import time
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from open_agent_compiler.runtime import ScriptTool

_GEMINI_MODEL = "gemini-2.5-flash"

_TRANSCRIBE_PROMPT = """Transcribe the speech in this video. Also note any significant visual content
(slides, diagrams, code on screen, important text overlays) with timestamps.

Return ONLY a JSON array of segments. Each segment must have:
- "timestamp": start time as "MM:SS" (e.g. "01:23")
- "end_timestamp": end time as "MM:SS"
- "text": the transcribed speech for that segment
- "visual_description": (optional) description of significant visual content on screen during this segment. Only include this field when there is something visually notable (a slide, diagram, code snippet, chart, etc.). Omit for talking-head segments.

Keep segments around 15-30 seconds each. Cover the entire video.
Return ONLY the JSON array, no markdown fences or other text."""


class TranscribeVideoInput(BaseModel):
    youtube_url: str = Field(description="YouTube video URL to download and transcribe")
    output_dir: str = Field(
        default=".agent_workspace",
        description="Directory to save the downloaded video",
    )


class TranscribeVideoOutput(BaseModel):
    transcript: list[dict] = Field(description="Timestamped transcript segments with optional visual descriptions")
    full_text: str = Field(description="Concatenated plain text transcript")
    video_path: str = Field(description="Path to the downloaded video file (for screenshots)")
    duration_seconds: float = Field(description="Total video duration in seconds")
    title: str = Field(description="Video title")


class TranscribeVideoTool(ScriptTool[TranscribeVideoInput, TranscribeVideoOutput]):
    name = "transcribe-video"
    description = "Download YouTube video and transcribe via Gemini with timestamps and visual descriptions"

    def execute(self, input: TranscribeVideoInput) -> TranscribeVideoOutput:
        out_dir = Path(input.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Download video (cap at 720p for manageable file size)
        result = subprocess.run(
            [
                "yt-dlp",
                "-f", "best[height<=720]",
                "--print-json",
                "-o", str(out_dir / "%(title)s.%(ext)s"),
                input.youtube_url,
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        metadata = json.loads(result.stdout.strip().split("\n")[-1])
        title = metadata.get("title", "Unknown")
        duration = float(metadata.get("duration", 0))

        # Find the downloaded video file
        video_path = metadata.get("filename") or metadata.get("_filename")
        if not video_path:
            requested = metadata.get("requested_downloads", [{}])
            if requested and "filepath" in requested[0]:
                video_path = requested[0]["filepath"]
        if not video_path or not Path(video_path).exists():
            # Fallback: find newest video in output dir
            video_exts = ("*.mp4", "*.webm", "*.mkv")
            candidates = []
            for ext in video_exts:
                candidates.extend(out_dir.glob(ext))
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            video_path = str(candidates[0]) if candidates else None
        if not video_path or not Path(video_path).exists():
            raise FileNotFoundError(f"Could not find downloaded video in {out_dir}")

        # Upload to Gemini and transcribe
        client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        uploaded = client.files.upload(file=video_path)

        # Wait for file to be processed
        while uploaded.state.name == "PROCESSING":
            time.sleep(2)
            uploaded = client.files.get(name=uploaded.name)

        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=[_TRANSCRIBE_PROMPT, uploaded],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        # Parse transcript
        raw_text = response.text.strip()
        transcript = json.loads(raw_text)

        full_text = " ".join(seg["text"] for seg in transcript)

        # Clean up uploaded file
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass

        return TranscribeVideoOutput(
            transcript=transcript,
            full_text=full_text,
            video_path=str(Path(video_path).resolve()),
            duration_seconds=duration,
            title=title,
        )


if __name__ == "__main__":
    TranscribeVideoTool.run()
