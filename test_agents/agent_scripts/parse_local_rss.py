#!/usr/bin/env python3
"""Local RSS/Atom feed parser — reads a local file and returns structured items."""

import re
from html.parser import HTMLParser
from pathlib import Path

import feedparser
from pydantic import BaseModel, Field

from open_agent_compiler.runtime import ScriptTool


class _HTMLStripper(HTMLParser):
    """Minimal HTML-to-text converter."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str):
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts).strip()


def _strip_html(html: str) -> str:
    if not html:
        return ""
    stripper = _HTMLStripper()
    stripper.feed(html)
    text = stripper.get_text()
    return re.sub(r"\s+", " ", text)


class ParseLocalRSSInput(BaseModel):
    file_path: str = Field(description="Path to the local RSS/Atom/XML feed file")
    max_items: int = Field(default=10, description="Maximum number of items to return")


class ParseLocalRSSOutput(BaseModel):
    items: list[dict] = Field(description="Parsed RSS items")
    feed_title: str = Field(description="Name of the feed")
    total_fetched: int = Field(description="Number of items returned")


class ParseLocalRSSTool(ScriptTool[ParseLocalRSSInput, ParseLocalRSSOutput]):
    name = "parse-local-rss"
    description = "Parse a local RSS/Atom feed file and return structured items"

    def execute(self, input: ParseLocalRSSInput) -> ParseLocalRSSOutput:
        path = Path(input.file_path)
        if not path.exists():
            raise FileNotFoundError(f"Feed file not found: {input.file_path}")

        feed = feedparser.parse(str(path))
        feed_title = feed.feed.get("title", path.name)

        items = []
        for entry in feed.entries[: input.max_items]:
            item = {
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "summary": _strip_html(entry.get("summary", "")),
            }
            # Include comments URL if present (e.g. HN feeds)
            if entry.get("comments"):
                item["comments_url"] = entry["comments"]
            items.append(item)

        return ParseLocalRSSOutput(
            items=items,
            feed_title=feed_title,
            total_fetched=len(items),
        )


if __name__ == "__main__":
    ParseLocalRSSTool.run()
