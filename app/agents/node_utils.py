"""Shared helpers for per-node logging and timing."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Generator


@contextmanager
def node_span(logger: logging.Logger, node_name: str, request_id: str) -> Generator[None, None, None]:
    """Log node start/finish with duration and safe metadata."""
    start = time.perf_counter()
    logger.info(
        "node_start",
        extra={"node_name": node_name, "request_id": request_id},
    )
    try:
        yield
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000.0, 3)
        logger.info(
            "node_finish",
            extra={
                "node_name": node_name,
                "request_id": request_id,
                "duration_ms": duration_ms,
            },
        )


def append_tool(used: list[str] | None, name: str) -> list[str]:
    """Immutable-style update for tool usage list."""
    base = list(used or [])
    base.append(name)
    return base
