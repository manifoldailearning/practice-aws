"""LangGraph orchestration for the Support Operations agent."""

from __future__ import annotations

import logging
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from app.agents.nodes.classify import build_classify_node
from app.agents.nodes.enrich import build_enrich_node
from app.agents.nodes.format_output import build_format_output_node
from app.agents.nodes.plan import build_plan_node
from app.agents.nodes.policy_lookup import build_policy_lookup_node
from app.agents.nodes.respond import build_respond_node
from app.agents.state import AgentState

logger = logging.getLogger(__name__)


def build_support_graph(llm: ChatOpenAI) -> Any:
    """Compile the LangGraph state machine (async nodes)."""
    builder = StateGraph(AgentState)

    builder.add_node("classify", build_classify_node(llm))
    builder.add_node("enrich", build_enrich_node(llm))
    builder.add_node("policy_lookup", build_policy_lookup_node(llm))
    builder.add_node("planning", build_plan_node(llm))
    builder.add_node("respond", build_respond_node(llm))
    builder.add_node("format_output", build_format_output_node())

    builder.add_edge(START, "classify")
    builder.add_edge("classify", "enrich")
    builder.add_edge("enrich", "policy_lookup")
    builder.add_edge("policy_lookup", "planning")
    builder.add_edge("planning", "respond")
    builder.add_edge("respond", "format_output")
    builder.add_edge("format_output", END)

    compiled = builder.compile()
    logger.info("LangGraph compiled", extra={"safe_metadata": {"nodes": 6}})
    return compiled
