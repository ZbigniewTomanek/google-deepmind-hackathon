"""Centralised logging configuration for NeoCortex services.

Call ``setup_logging(service_name)`` once at the top of each entry-point,
before any other code that uses ``logger``.  The function is idempotent.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from loguru import Record

_LOGGING_CONFIGURED = False


def _action_log_filter(record: Record) -> bool:
    """Only allow messages that carry ``action_log=True``."""
    return record["extra"].get("action_log", False)


def setup_logging(service_name: str = "neocortex") -> None:
    """Configure loguru sinks for *service_name*.

    Sinks
    -----
    1. **stderr** -- human-readable, coloured output (terminal / Docker).
    2. **log/{service_name}.log** -- rotating file, same format sans colour.
    3. **log/agent_actions.log** -- structured JSON audit trail
       (only messages with ``action_log=True``).

    The log level is controlled by ``NEOCORTEX_LOG_LEVEL`` (default ``INFO``).
    """
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    log_level = os.getenv("NEOCORTEX_LOG_LEVEL", "INFO").upper()
    log_dir = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "log")
    log_dir = os.path.normpath(log_dir)
    os.makedirs(log_dir, exist_ok=True)

    logger.remove()  # drop default stderr handler

    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    fmt_plain = "{time:YYYY-MM-DD HH:mm:ss.SSS} | " "{level: <8} | " "{name}:{function}:{line} | " "{message}"

    # 1. stderr
    logger.add(
        sys.stderr,
        level=log_level,
        format=fmt,
        backtrace=False,
        diagnose=False,
    )

    # 2. rotating service log
    logger.add(
        os.path.join(log_dir, f"{service_name}.log"),
        level=log_level,
        format=fmt_plain,
        rotation="10 MB",
        retention="7 days",
        backtrace=True,
        diagnose=False,
    )

    # 3. agent action audit trail (JSON, filtered)
    logger.add(
        os.path.join(log_dir, "agent_actions.log"),
        level="INFO",
        format="{message}",
        filter=_action_log_filter,
        serialize=True,
        rotation="10 MB",
        retention="7 days",
    )

    _LOGGING_CONFIGURED = True
    logger.debug("Logging configured for service={}", service_name)
