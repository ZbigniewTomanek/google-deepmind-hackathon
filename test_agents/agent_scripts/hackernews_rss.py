#!/usr/bin/env python3
"""HackerNews RSS feed parser — fetches and structures HN stories for agent ingestion."""

import re
from html.parser import HTMLParser

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


class HackerNewsRSSInput(BaseModel):
    feed_url: str = Field(
        default="https://hnrss.org/newest",
        description="RSS feed URL (defaults to HN newest)",
    )
    max_items: int = Field(default=10, description="Maximum number of items to return")


class HackerNewsRSSOutput(BaseModel):
    items: list[dict] = Field(description="Parsed RSS items")
    feed_title: str = Field(description="Name of the feed")
    total_fetched: int = Field(description="Number of items returned")


class HackerNewsRSSTool(ScriptTool[HackerNewsRSSInput, HackerNewsRSSOutput]):
    name = "hackernews-rss"
    description = "Parse an RSS feed (defaults to HackerNews) and return structured items"

    def execute(self, input: HackerNewsRSSInput) -> HackerNewsRSSOutput:
        feed = feedparser.parse(input.feed_url)
        feed_title = feed.feed.get("title", input.feed_url)

        items = []
        for entry in feed.entries[: input.max_items]:
            item = {
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "summary": _strip_html(entry.get("summary", "")),
                "comments_url": entry.get("comments", ""),
            }
            items.append(item)

        return HackerNewsRSSOutput(
            items=items,
            feed_title=feed_title,
            total_fetched=len(items),
        )


if __name__ == "__main__":
    HackerNewsRSSTool.run()
