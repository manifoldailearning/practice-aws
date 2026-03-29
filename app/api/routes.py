"""HTTP routes."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from langchain_core.runnables import RunnableConfig
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
from app.core.log_safety import truncate_for_log
from app.core.langsmith_tracing import graph_run_config
from app.core.metrics import REGISTRY, monotonic_ms
from app.core.prometheus_metrics import AGENT_INVOCATIONS
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
        demo_scenarios_enabled=settings.enable_demo_scenarios,
        demo_slow_tool_delay_seconds=settings.demo_slow_tool_delay_seconds,
    )


@router.post("/agent/respond", response_model=AgentRespondResponse)
async def agent_respond(request: Request, body: AgentRespondRequest) -> AgentRespondResponse:
    """Run full LangGraph pipeline and return structured JSON."""
    rid = _get_request_id(request)
    graph = request.app.state.graph
    settings = get_settings()
    t0 = monotonic_ms()
    REGISTRY.record_agent_invocation()
    AGENT_INVOCATIONS.labels(endpoint="/agent/respond").inc()
    initial: AgentState = {
        "user_query": body.user_query,
        "request_id": rid,
        "used_tools": [],
    }
    run_cfg = graph_run_config(
        request_id=rid,
        environment=settings.environment,
        endpoint="/agent/respond",
    )
    cap = settings.agent_io_log_max_chars
    uq_preview = truncate_for_log(body.user_query, cap)
    logger.info(
        "Agent user input",
        extra={
            "log_event": "agent_user_input",
            "safe_metadata": {
                "request_id": rid,
                "endpoint": "/agent/respond",
                "user_query_preview": uq_preview,
            },
        },
    )
    try:
        final = await asyncio.wait_for(
            graph.ainvoke(initial, config=run_cfg),
            timeout=settings.request_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        logger.error(
            "Agent execution timed out",
            extra={
                "request_id": rid,
                "error_code": "AGENT_TIMEOUT",
                "error_type": "TimeoutError",
                "log_event": "agent_timeout",
                "safe_metadata": {
                    "endpoint": "/agent/respond",
                    "request_id": rid,
                    "user_query_preview": uq_preview,
                },
            },
        )
        raise HTTPException(status_code=504, detail="Agent execution timed out") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Agent invocation failed",
            extra={
                "request_id": rid,
                "error_code": "AGENT_INVOCATION_FAILED",
                "error_type": type(exc).__name__,
                "log_event": "agent_invocation_error",
                "safe_metadata": {
                    "endpoint": "/agent/respond",
                    "request_id": rid,
                    "user_query_preview": uq_preview,
                },
            },
        )
        raise AgentInvocationError("Agent execution failed") from exc

    latency = monotonic_ms() - t0

    logger.info(
        "Agent structured output",
        extra={
            "log_event": "agent_output",
            "safe_metadata": {
                "request_id": rid,
                "endpoint": "/agent/respond",
                "classification": str(final.get("classification", "")),
                "draft_reply_preview": truncate_for_log(str(final.get("draft_reply", "")), cap),
                "internal_summary_preview": truncate_for_log(str(final.get("internal_summary", "")), cap),
                "recommended_action_preview": truncate_for_log(str(final.get("recommended_action", "")), cap),
                "policy_context_preview": truncate_for_log(str(final.get("policy_context", "")), cap),
                "used_tools": list(final.get("used_tools") or []),
                "processing_time_ms": round(latency, 3),
            },
        },
    )

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


async def _sse_updates(
    graph: Any, initial: AgentState, run_cfg: RunnableConfig
) -> AsyncIterator[bytes]:
    """Stream LangGraph update chunks as SSE."""
    yield _sse_event("start", {"request_id": initial.get("request_id")})
    try:
        async for chunk in graph.astream(initial, stream_mode="updates", config=run_cfg):
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
    settings = get_settings()
    initial: AgentState = {
        "user_query": body.user_query,
        "request_id": rid,
        "used_tools": [],
    }
    run_cfg = graph_run_config(
        request_id=rid,
        environment=settings.environment,
        endpoint="/agent/stream",
    )
    cap = settings.agent_io_log_max_chars
    logger.info(
        "Agent user input (stream)",
        extra={
            "log_event": "agent_user_input",
            "safe_metadata": {
                "request_id": rid,
                "endpoint": "/agent/stream",
                "user_query_preview": truncate_for_log(body.user_query, cap),
            },
        },
    )

    async def gen() -> AsyncIterator[bytes]:
        REGISTRY.record_agent_invocation()
        AGENT_INVOCATIONS.labels(endpoint="/agent/stream").inc()
        async for part in _sse_updates(graph, initial, run_cfg):
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
