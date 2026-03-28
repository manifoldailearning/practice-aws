"""Pydantic request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentRespondRequest(BaseModel):
    """Inbound support / ops query."""

    user_query: str = Field(..., min_length=1, max_length=16000)


class AgentRespondResponse(BaseModel):
    """Structured agent output for operators."""

    request_id: str
    classification: str
    policy_context: str
    recommended_action: str
    draft_reply: str
    internal_summary: str
    used_tools: list[str]
    processing_time_ms: float


class HealthResponse(BaseModel):
    """Liveness payload."""

    status: str = "ok"


class ReadyResponse(BaseModel):
    """Readiness payload."""

    ready: bool
    checks: dict[str, str]


class ConfigCheckResponse(BaseModel):
    """Non-sensitive configuration snapshot."""

    environment: str
    configured_model: str
    cloudwatch_enabled: bool
    aws_region: str
    secret_provider_type: str


class MetricsSummaryResponse(BaseModel):
    """In-process metrics."""

    request_count: int
    success_count: int
    failure_count: int
    average_latency_ms: float
    agent_invocation_count: int
