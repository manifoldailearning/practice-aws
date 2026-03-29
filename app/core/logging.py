"""Structured JSON logging with optional CloudWatch (watchtower)."""

from __future__ import annotations

import json
import logging
import sys
import traceback
import uuid
from datetime import datetime, timezone
from logging import Handler, LogRecord
from typing import Any

from app.core.config import Settings, get_settings
from app.services.request_context import get_request_context

_LOG_INITIALIZED = False


class JsonFormatter(logging.Formatter):
    """Serialize log records as single-line JSON for stdout / aggregators."""

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    def format(self, record: LogRecord) -> str:
        ctx = get_request_context()
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "environment": self._settings.environment,
            "request_id": ctx.request_id if ctx else getattr(record, "request_id", None),
            "route": ctx.route if ctx else getattr(record, "route", None),
        }
        if getattr(record, "node_name", None):
            payload["node_name"] = record.node_name
        if getattr(record, "duration_ms", None) is not None:
            payload["duration_ms"] = record.duration_ms
        if record.exc_info:
            payload["exception"] = "".join(traceback.format_exception_only(record.exc_info[1]))
        if getattr(record, "error_code", None):
            payload["error_code"] = record.error_code
        if getattr(record, "error_type", None):
            payload["error_type"] = record.error_type
        if getattr(record, "log_event", None):
            payload["log_event"] = record.log_event
        extra = getattr(record, "safe_metadata", None)
        if isinstance(extra, dict):
            payload["metadata"] = extra
        return json.dumps(payload, default=str)


def _safe_add_watchtower_handler(settings: Settings, root: logging.Logger) -> None:
    """Attach CloudWatch handler; never raise to caller."""
    try:
        import watchtower

        stream = f"{settings.cloudwatch_log_stream_prefix}/{uuid.uuid4().hex[:12]}"
        wh = watchtower.CloudWatchLogHandler(
            log_group=settings.cloudwatch_log_group,
            stream_name=stream,
            boto3_client=None,
            create_log_group=True,
        )
        wh.setLevel(logging.INFO)
        wh.setFormatter(JsonFormatter(settings))
        root.addHandler(wh)
    except Exception as exc:  # noqa: BLE001 — graceful degradation
        root.warning("CloudWatch logging disabled due to setup failure: %s", type(exc).__name__)


def setup_logging(settings: Settings | None = None) -> None:
    """Configure root logger: JSON to stdout; optional CloudWatch."""
    global _LOG_INITIALIZED
    if _LOG_INITIALIZED:
        return
    s = settings or get_settings()
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(s.log_level.upper())

    stdout = logging.StreamHandler(sys.stdout)
    stdout.setLevel(s.log_level.upper())
    stdout.setFormatter(JsonFormatter(s))
    root.addHandler(stdout)

    if s.enable_cloudwatch_logging:
        _safe_add_watchtower_handler(s, root)

    _LOG_INITIALIZED = True


def reset_logging_for_tests() -> None:
    """Reset logging state (tests only)."""
    global _LOG_INITIALIZED
    _LOG_INITIALIZED = False
    logging.getLogger().handlers.clear()
