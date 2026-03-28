"""Policy retrieval node — search_bootcamp_policy_tool."""

from __future__ import annotations

import asyncio
import logging

from langchain_openai import ChatOpenAI

from app.agents.node_utils import append_tool, node_span
from app.agents.state import AgentState
from app.tools.policy_tools import search_bootcamp_policy_tool

logger = logging.getLogger(__name__)


def build_policy_lookup_node(_llm: ChatOpenAI):
    """Factory for policy lookup node."""

    async def policy_lookup_node(state: AgentState) -> AgentState:
        rid = state.get("request_id", "")
        with node_span(logger, "policy_lookup", rid):
            q = state.get("user_query", "")
            enriched = state.get("enriched_context", "")
            query = f"{q}\n\nContext bullets:\n{enriched}"

            def _run_tool() -> str:
                return str(search_bootcamp_policy_tool.invoke({"query": query}))

            policy_text = await asyncio.to_thread(_run_tool)
            used = append_tool(state.get("used_tools"), "search_bootcamp_policy_tool")
            return {
                "policy_context": policy_text,
                "used_tools": used,
            }

    return policy_lookup_node
