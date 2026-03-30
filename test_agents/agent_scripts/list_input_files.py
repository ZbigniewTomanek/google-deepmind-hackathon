#!/usr/bin/env python3
"""List files in a directory with file types and sizes."""

from pathlib import Path

from pydantic import BaseModel, Field

from open_agent_compiler.runtime import ScriptTool


class ListInputFilesInput(BaseModel):
    directory: str = Field(
        default="/app/input",
        description="Directory to list files from",
    )


class ListInputFilesOutput(BaseModel):
    files: list[dict] = Field(description="List of files with name, path, extension, and size_bytes")
    total_count: int = Field(description="Total number of files found")


class ListInputFilesTool(ScriptTool[ListInputFilesInput, ListInputFilesOutput]):
    name = "list-input-files"
    description = "List files in a directory with file extensions and sizes"

    def execute(self, input: ListInputFilesInput) -> ListInputFilesOutput:
        directory = Path(input.directory)
        if not directory.exists():
            return ListInputFilesOutput(files=[], total_count=0)

        files = []
        for path in sorted(directory.iterdir()):
            if not path.is_file():
                continue
            files.append({
                "name": path.name,
                "path": str(path.resolve()),
                "extension": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
            })

        return ListInputFilesOutput(files=files, total_count=len(files))


if __name__ == "__main__":
    ListInputFilesTool.run()
