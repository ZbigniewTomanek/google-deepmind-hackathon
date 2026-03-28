#!/usr/bin/env python3
"""Video screenshot tool — extracts a frame at a given timestamp using ffmpeg."""

import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from open_agent_compiler.runtime import ScriptTool


class VideoScreenshotInput(BaseModel):
    video_path: str = Field(description="Path to the video file")
    timestamp: str = Field(description="Timestamp in MM:SS or HH:MM:SS format")
    output_dir: str = Field(
        default=".agent_workspace",
        description="Directory to save the screenshot",
    )


class VideoScreenshotOutput(BaseModel):
    screenshot_path: str = Field(description="Absolute path to the extracted frame")
    timestamp: str = Field(description="The requested timestamp")


class VideoScreenshotTool(ScriptTool[VideoScreenshotInput, VideoScreenshotOutput]):
    name = "video-screenshot"
    description = "Extract a frame from a video at a specific timestamp"

    def execute(self, input: VideoScreenshotInput) -> VideoScreenshotOutput:
        video = Path(input.video_path)
        if not video.exists():
            raise FileNotFoundError(f"Video not found: {input.video_path}")

        out_dir = Path(input.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        safe_ts = input.timestamp.replace(":", "-")
        output_name = f"screenshot_{video.stem}_{safe_ts}.jpg"
        output_path = out_dir / output_name

        subprocess.run(
            [
                "ffmpeg",
                "-ss", input.timestamp,
                "-i", str(video),
                "-frames:v", "1",
                "-q:v", "2",
                "-y",
                str(output_path),
            ],
            capture_output=True,
            check=True,
        )

        if not output_path.exists():
            raise RuntimeError(f"ffmpeg did not produce output at {output_path}")

        return VideoScreenshotOutput(
            screenshot_path=str(output_path.resolve()),
            timestamp=input.timestamp,
        )


if __name__ == "__main__":
    VideoScreenshotTool.run()
