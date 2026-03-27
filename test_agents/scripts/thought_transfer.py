#!/usr/bin/env python3
"""File-based inter-agent data passing.

Provides simple key-value read/write in .agent_workspace/ for passing
data between orchestrators and subagents via thought-transfer pattern.

Usage:
    uv run scripts/thought_transfer.py write <key> --stdin
    uv run scripts/thought_transfer.py read <key>
    uv run scripts/thought_transfer.py list
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WORKSPACE = Path(".agent_workspace")


def _ensure_workspace() -> Path:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    return WORKSPACE


def cmd_write(key: str) -> None:
    ws = _ensure_workspace()
    content = sys.stdin.read()
    (ws / f"{key}.json").write_text(content)
    print(json.dumps({"success": True, "key": key, "bytes": len(content)}))


def cmd_read(key: str) -> None:
    ws = _ensure_workspace()
    target = ws / f"{key}.json"
    if not target.exists():
        print(json.dumps({"success": False, "error": f"Key not found: {key}"}))
        sys.exit(1)
    content = target.read_text()
    print(json.dumps({"success": True, "key": key, "content": content}))


def cmd_list() -> None:
    ws = _ensure_workspace()
    keys = sorted(p.stem for p in ws.glob("*.json"))
    print(json.dumps({"success": True, "keys": keys, "count": len(keys)}))


def main() -> None:
    parser = argparse.ArgumentParser(prog="thought-transfer", description="Inter-agent data passing")
    sub = parser.add_subparsers(dest="command", required=True)

    write_p = sub.add_parser("write", help="Write data (reads from stdin)")
    write_p.add_argument("key", help="Data key name")

    read_p = sub.add_parser("read", help="Read data by key")
    read_p.add_argument("key", help="Data key name")

    sub.add_parser("list", help="List all stored keys")

    args = parser.parse_args()

    if args.command == "write":
        cmd_write(args.key)
    elif args.command == "read":
        cmd_read(args.key)
    elif args.command == "list":
        cmd_list()


if __name__ == "__main__":
    main()
