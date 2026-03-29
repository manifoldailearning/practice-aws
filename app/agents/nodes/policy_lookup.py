"""Policy retrieval node — search_bootcamp_policy_tool."""

from __future__ import annotations

import asyncio
import logging

from langchain_openai import ChatOpenAI

from app.agents.node_utils import append_tool, node_span
from app.agents.state import AgentState
from app.core.config import get_settings
from app.core.demo_scenarios import resolve_demo_policy_lookup
from app.tools.policy_tools import search_bootcamp_policy_tool

logger = logging.getLogger(__name__)


def build_policy_lookup_node(_llm: ChatOpenAI):
    """Factory for policy lookup node."""

    async def policy_lookup_node(state: AgentState) -> AgentState:
        rid = state.get("request_id", "")
        with node_span(logger, "policy_lookup", rid):
            q = state.get("user_query", "")
            enriched = state.get("enriched_context", "")
            settings = get_settings()
            branch = resolve_demo_policy_lookup(q, settings)
            if branch == "failure":
                logger.error(
                    "Demo: simulated policy tool failure before invoke",
                    extra={
                        "log_event": "demo_tool_failure",
                        "request_id": rid,
                        "safe_metadata": {
                            "node": "policy_lookup",
                            "tool": "search_bootcamp_policy_tool",
                            "trigger": "demo_tool_failure_substring",
                        },
                    },
                )
                raise RuntimeError(
                    "Simulated search_bootcamp_policy_tool failure (classroom demo — see ENABLE_DEMO_SCENARIOS)"
                )
            if branch == "slow":
                delay = settings.demo_slow_tool_delay_seconds
                logger.info(
                    "Demo: slow policy tool (sleep before search_bootcamp_policy_tool)",
                    extra={
                        "log_event": "demo_slow_tool_start",
                        "request_id": rid,
                        "safe_metadata": {
                            "node": "policy_lookup",
                            "tool": "search_bootcamp_policy_tool",
                            "delay_seconds": delay,
                        },
                    },
                )
                await asyncio.sleep(delay)
                logger.info(
                    "Demo: slow policy tool sleep finished; invoking tool",
                    extra={
                        "log_event": "demo_slow_tool_end",
                        "request_id": rid,
                        "safe_metadata": {"node": "policy_lookup", "delay_seconds": delay},
                    },
                )
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
