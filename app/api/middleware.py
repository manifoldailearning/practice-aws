"""Request ID middleware and correlation."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.services.request_context import RequestContext, clear_request_context, set_request_context


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign X-Request-ID (or generate), bind contextvars for logging."""

    async def dispatch(self, request: Request, call_next) -> Response:
        header_rid = request.headers.get("x-request-id") or request.headers.get("X-Request-ID")
        rid = header_rid or str(uuid.uuid4())
        route = request.url.path
        ctx = RequestContext(request_id=rid, route=route)
        set_request_context(ctx)
        try:
            response = await call_next(request)
        finally:
            clear_request_context()
        response.headers["X-Request-ID"] = rid
        return response
