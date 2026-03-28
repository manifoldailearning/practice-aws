"""Context enrichment node — condense learner intent for downstream steps."""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agents.node_utils import node_span
from app.agents.state import AgentState
from app.core.llm import ainvoke_with_retry

logger = logging.getLogger(__name__)


def build_enrich_node(llm: ChatOpenAI):
    """Factory for enrichment node."""

    async def enrich_node(state: AgentState) -> AgentState:
        rid = state.get("request_id", "")
        with node_span(logger, "enrich", rid):
            q = state.get("user_query", "")
            sys = SystemMessage(
                content=(
                    "You are an internal support analyst. Summarize the learner or operator "
                    "intent in 2-4 short bullet phrases. No PII beyond what is in the query."
                )
            )
            human = HumanMessage(content=q)
            resp = await ainvoke_with_retry(llm, [sys, human])
            text = getattr(resp, "content", str(resp))
            return {"enriched_context": str(text)}

    return enrich_node
