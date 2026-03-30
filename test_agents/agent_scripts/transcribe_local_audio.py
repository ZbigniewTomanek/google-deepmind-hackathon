#!/usr/bin/env python3
"""Local audio transcription tool — transcribes a local audio file via Gemini API."""

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


class TranscribeLocalAudioInput(BaseModel):
    audio_path: str = Field(description="Path to the local audio file to transcribe")
    output_dir: str = Field(
        default=".agent_workspace",
        description="Directory for temporary files",
    )


class TranscribeLocalAudioOutput(BaseModel):
    transcript: list[dict] = Field(description="Timestamped transcript segments")
    full_text: str = Field(description="Concatenated plain text transcript")
    audio_path: str = Field(description="Absolute path to the audio file")
    duration_seconds: float = Field(description="Total audio duration in seconds")
    title: str = Field(description="Audio title (derived from filename)")


class TranscribeLocalAudioTool(ScriptTool[TranscribeLocalAudioInput, TranscribeLocalAudioOutput]):
    name = "transcribe-local-audio"
    description = "Transcribe a local audio file via Gemini with timestamps"

    def execute(self, input: TranscribeLocalAudioInput) -> TranscribeLocalAudioOutput:
        audio = Path(input.audio_path)
        if not audio.exists():
            raise FileNotFoundError(f"Audio not found: {input.audio_path}")

        title = audio.stem

        # Get duration via ffprobe
        duration = 0.0
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    str(audio),
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
        uploaded = client.files.upload(file=str(audio))

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

        return TranscribeLocalAudioOutput(
            transcript=transcript,
            full_text=full_text,
            audio_path=str(audio.resolve()),
            duration_seconds=duration,
            title=title,
        )


if __name__ == "__main__":
    TranscribeLocalAudioTool.run()
