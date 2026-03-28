"""Classification node — issue taxonomy via classify_issue_tool."""

from __future__ import annotations

import asyncio
import logging

from langchain_openai import ChatOpenAI

from app.agents.node_utils import append_tool, node_span
from app.agents.state import AgentState
from app.tools.classification_tools import classify_issue_tool

logger = logging.getLogger(__name__)


def build_classify_node(_llm: ChatOpenAI):
    """Factory: returns async graph node callable."""

    async def classify_node(state: AgentState) -> AgentState:
        rid = state.get("request_id", "")
        with node_span(logger, "classify", rid):
            raw = state.get("user_query", "")

            def _run_tool() -> str:
                return str(classify_issue_tool.invoke({"message": raw})).strip()

            classification = await asyncio.to_thread(_run_tool)
            used = append_tool(state.get("used_tools"), "classify_issue_tool")
            return {
                "classification": classification,
                "used_tools": used,
            }

    return classify_node
