#!/usr/bin/env python3
"""Todo list management tool for the task subagent."""

import json
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from open_agent_compiler.runtime import ScriptTool

TASKS_FILE = Path(".agent_workspace/tasks.json")


def _load_tasks() -> list[dict]:
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if TASKS_FILE.exists():
        return json.loads(TASKS_FILE.read_text())
    return []


def _save_tasks(tasks: list[dict]) -> None:
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(json.dumps(tasks, indent=2))


class TaskInput(BaseModel):
    action: str = Field(description="Action: add, list, complete, delete")
    title: str = Field(default="", description="Task title (for add action)")
    task_id: str = Field(default="", description="Task ID (for complete/delete actions)")


class TaskOutput(BaseModel):
    tasks: list[dict]
    message: str


class TaskManagerTool(ScriptTool[TaskInput, TaskOutput]):
    name = "task-manager"
    description = "Manage a todo list: add, list, complete, or delete tasks"

    def execute(self, input: TaskInput) -> TaskOutput:
        tasks = _load_tasks()

        if input.action == "add":
            if not input.title:
                return TaskOutput(tasks=tasks, message="Error: title is required for add action")
            new_task = {"id": uuid.uuid4().hex[:8], "title": input.title, "status": "pending"}
            tasks.append(new_task)
            _save_tasks(tasks)
            return TaskOutput(tasks=tasks, message=f"Added task: {input.title}")

        elif input.action == "list":
            return TaskOutput(tasks=tasks, message=f"Found {len(tasks)} task(s)")

        elif input.action == "complete":
            for t in tasks:
                if t["id"] == input.task_id:
                    t["status"] = "completed"
                    _save_tasks(tasks)
                    return TaskOutput(tasks=tasks, message=f"Completed task: {t['title']}")
            return TaskOutput(tasks=tasks, message=f"Task not found: {input.task_id}")

        elif input.action == "delete":
            before = len(tasks)
            tasks = [t for t in tasks if t["id"] != input.task_id]
            _save_tasks(tasks)
            if len(tasks) < before:
                return TaskOutput(tasks=tasks, message=f"Deleted task: {input.task_id}")
            return TaskOutput(tasks=tasks, message=f"Task not found: {input.task_id}")

        else:
            return TaskOutput(tasks=tasks, message=f"Unknown action: {input.action}")


if __name__ == "__main__":
    TaskManagerTool.run()
