#!/usr/bin/env python3
"""Local video transcription tool — transcribes a local video file via Gemini API with visual descriptions."""

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


class TranscribeLocalVideoInput(BaseModel):
    video_path: str = Field(description="Path to the local video file to transcribe")
    output_dir: str = Field(
        default=".agent_workspace",
        description="Directory for temporary files",
    )


class TranscribeLocalVideoOutput(BaseModel):
    transcript: list[dict] = Field(description="Timestamped transcript segments with optional visual descriptions")
    full_text: str = Field(description="Concatenated plain text transcript")
    video_path: str = Field(description="Absolute path to the video file (for screenshots)")
    duration_seconds: float = Field(description="Total video duration in seconds")
    title: str = Field(description="Video title (derived from filename)")


class TranscribeLocalVideoTool(ScriptTool[TranscribeLocalVideoInput, TranscribeLocalVideoOutput]):
    name = "transcribe-local-video"
    description = "Transcribe a local video file via Gemini with timestamps and visual descriptions"

    def execute(self, input: TranscribeLocalVideoInput) -> TranscribeLocalVideoOutput:
        video = Path(input.video_path)
        if not video.exists():
            raise FileNotFoundError(f"Video not found: {input.video_path}")

        title = video.stem

        # Get duration via ffprobe
        duration = 0.0
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    str(video),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            probe = json.loads(result.stdout)
            duration = float(probe.get("format", {}).get("duration", 0))
        except (subprocess.CalledProcessError, json.JSONDecodeError, ValueError):
            pass

        # Upload to Gemini and transcribe
        client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        uploaded = client.files.upload(file=str(video))

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

        return TranscribeLocalVideoOutput(
            transcript=transcript,
            full_text=full_text,
            video_path=str(video.resolve()),
            duration_seconds=duration,
            title=title,
        )


if __name__ == "__main__":
    TranscribeLocalVideoTool.run()
