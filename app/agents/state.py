"""Typed graph state for the Support Operations agent."""

from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict, total=False):
    """State flowing through LangGraph nodes; keys are incrementally merged."""

    user_query: str
    request_id: str
    classification: str
    policy_context: str
    enriched_context: str
    plan: str
    draft_reply: str
    internal_summary: str
    recommended_action: str
    used_tools: list[str]
    processing_notes: str
    error: str | None
