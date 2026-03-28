"""Request-scoped context (request id, route) via contextvars."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    """Correlation data for a single HTTP request."""

    request_id: str
    route: str


_ctx: ContextVar[RequestContext | None] = ContextVar("request_context", default=None)


def set_request_context(ctx: RequestContext) -> None:
    """Bind context for the current async task."""
    _ctx.set(ctx)


def get_request_context() -> RequestContext | None:
    """Current request context, if any."""
    return _ctx.get()


def clear_request_context() -> None:
    """Remove binding (optional cleanup)."""
    _ctx.set(None)
