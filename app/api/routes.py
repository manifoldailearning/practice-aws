"""HTTP routes."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.agents.state import AgentState
from app.api.schemas import (
    AgentRespondRequest,
    AgentRespondResponse,
    ConfigCheckResponse,
    HealthResponse,
    MetricsSummaryResponse,
    ReadyResponse,
)
from app.core.config import get_settings
from app.core.exceptions import AgentInvocationError
from app.core.metrics import REGISTRY, monotonic_ms
from app.core.readiness import ReadinessService
from app.services.request_context import get_request_context

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_request_id(request: Request) -> str:
    ctx = get_request_context()
    if ctx:
        return ctx.request_id
    return request.headers.get("x-request-id") or getattr(request.state, "request_id", "unknown")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness: process is up."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
async def ready(request: Request) -> ReadyResponse:
    """Readiness: config + secrets loadable (no secret values returned)."""
    prov = request.app.state.secrets_provider
    rs = ReadinessService()
    result = rs.check(secrets=prov)
    if not result.ready:
        raise HTTPException(status_code=503, detail=result.to_public_dict())
    return ReadyResponse(ready=True, checks=result.checks)


@router.get("/metrics-summary", response_model=MetricsSummaryResponse)
async def metrics_summary() -> MetricsSummaryResponse:
    """Lightweight JSON metrics."""
    s = REGISTRY.summary()
    return MetricsSummaryResponse(
        request_count=int(s["request_count"]),
        success_count=int(s["success_count"]),
        failure_count=int(s["failure_count"]),
        average_latency_ms=float(s["average_latency_ms"]),
        agent_invocation_count=int(s["agent_invocation_count"]),
    )


@router.get("/config/check", response_model=ConfigCheckResponse)
async def config_check(request: Request) -> ConfigCheckResponse:
    """Safe configuration metadata only."""
    settings = get_settings()
    prov = request.app.state.secrets_provider
    return ConfigCheckResponse(
        environment=settings.environment,
        configured_model=settings.openai_model,
        cloudwatch_enabled=settings.enable_cloudwatch_logging,
        aws_region=settings.aws_region,
        secret_provider_type=prov.provider_type,
    )


@router.post("/agent/respond", response_model=AgentRespondResponse)
async def agent_respond(request: Request, body: AgentRespondRequest) -> AgentRespondResponse:
    """Run full LangGraph pipeline and return structured JSON."""
    rid = _get_request_id(request)
    graph = request.app.state.graph
    settings = get_settings()
    t0 = monotonic_ms()
    REGISTRY.record_agent_invocation()
    initial: AgentState = {
        "user_query": body.user_query,
        "request_id": rid,
        "used_tools": [],
    }
    try:
        final = await asyncio.wait_for(
            graph.ainvoke(initial),
            timeout=settings.request_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Agent execution timed out") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Agent invocation failed", extra={"request_id": rid})
        raise AgentInvocationError("Agent execution failed") from exc

    latency = monotonic_ms() - t0

    return AgentRespondResponse(
        request_id=rid,
        classification=str(final.get("classification", "")),
        policy_context=str(final.get("policy_context", "")),
        recommended_action=str(final.get("recommended_action", "")),
        draft_reply=str(final.get("draft_reply", "")),
        internal_summary=str(final.get("internal_summary", "")),
        used_tools=list(final.get("used_tools") or []),
        processing_time_ms=round(latency, 3),
    )


async def _sse_updates(graph: Any, initial: AgentState) -> AsyncIterator[bytes]:
    """Stream LangGraph update chunks as SSE."""
    yield _sse_event("start", {"request_id": initial.get("request_id")})
    try:
        async for chunk in graph.astream(initial, stream_mode="updates"):
            yield _sse_event("update", chunk)
        yield _sse_event("done", {})
    except Exception as exc:  # noqa: BLE001
        yield _sse_event("error", {"type": type(exc).__name__, "message": "agent_stream_failed"})


def _sse_event(event: str, data: Any) -> bytes:
    payload = json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


@router.post("/agent/stream")
async def agent_stream(request: Request, body: AgentRespondRequest) -> StreamingResponse:
    """Server-Sent Events stream of graph updates (and optional token stream later)."""
    rid = _get_request_id(request)
    graph = request.app.state.graph
    initial: AgentState = {
        "user_query": body.user_query,
        "request_id": rid,
        "used_tools": [],
    }

    async def gen() -> AsyncIterator[bytes]:
        REGISTRY.record_agent_invocation()
        async for part in _sse_updates(graph, initial):
            yield part

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Request-ID": rid,
            "Connection": "keep-alive",
        },
    )
