"""Backward-compatibility shim — use episode_processor.py instead."""

from neocortex.ingestion.episode_processor import EpisodeProcessor as StubProcessor

__all__ = ["StubProcessor"]
