#!/usr/bin/env python3
"""YouTube audio transcription tool — downloads audio and transcribes via Gemini API."""

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

_TRANSCRIBE_PROMPT = """Transcribe this audio. Return ONLY a JSON array of segments.
Each segment must have:
- "timestamp": start time as "MM:SS" (e.g. "01:23")
- "end_timestamp": end time as "MM:SS"
- "text": the transcribed speech for that segment

Keep segments around 15-30 seconds each. Cover the entire audio.
Return ONLY the JSON array, no markdown fences or other text."""


class TranscribeAudioInput(BaseModel):
    youtube_url: str = Field(description="YouTube video URL to download audio from")
    output_dir: str = Field(
        default=".agent_workspace",
        description="Directory to save the downloaded audio",
    )


class TranscribeAudioOutput(BaseModel):
    transcript: list[dict] = Field(description="Timestamped transcript segments")
    full_text: str = Field(description="Concatenated plain text transcript")
    audio_path: str = Field(description="Path to the downloaded audio file")
    duration_seconds: float = Field(description="Total audio duration in seconds")
    title: str = Field(description="Video title")


class TranscribeAudioTool(ScriptTool[TranscribeAudioInput, TranscribeAudioOutput]):
    name = "transcribe-audio"
    description = "Download YouTube audio and transcribe it via Gemini with timestamps"

    def execute(self, input: TranscribeAudioInput) -> TranscribeAudioOutput:
        out_dir = Path(input.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Download audio with yt-dlp
        result = subprocess.run(
            [
                "yt-dlp",
                "-x",
                "--audio-format", "mp3",
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

        # Find the downloaded mp3 file
        audio_path = None
        requested_path = metadata.get("requested_downloads", [{}])
        if requested_path and "filepath" in requested_path[0]:
            audio_path = requested_path[0]["filepath"]
        if not audio_path:
            # Fallback: find newest mp3 in output dir
            mp3s = sorted(out_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
            audio_path = str(mp3s[0]) if mp3s else None
        if not audio_path or not Path(audio_path).exists():
            raise FileNotFoundError(f"Could not find downloaded audio in {out_dir}")

        # Upload to Gemini and transcribe
        client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        uploaded = client.files.upload(file=audio_path)

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

        return TranscribeAudioOutput(
            transcript=transcript,
            full_text=full_text,
            audio_path=str(Path(audio_path).resolve()),
            duration_seconds=duration,
            title=title,
        )


if __name__ == "__main__":
    TranscribeAudioTool.run()
