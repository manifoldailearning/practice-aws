"""Response generation — draft_response_tool + polished learner-facing reply."""

from __future__ import annotations

import asyncio
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agents.node_utils import append_tool, node_span
from app.agents.state import AgentState
from app.core.llm import ainvoke_with_retry
from app.tools.drafting_tools import draft_response_tool

logger = logging.getLogger(__name__)


def build_respond_node(llm: ChatOpenAI):
    """Factory for response generation node."""

    async def respond_node(state: AgentState) -> AgentState:
        rid = state.get("request_id", "")
        with node_span(logger, "respond", rid):
            classification = state.get("classification", "")
            policy = state.get("policy_context", "")
            enriched = state.get("enriched_context", "")
            plan = state.get("plan", "")

            def _draft() -> str:
                return str(
                    draft_response_tool.invoke(
                        {
                            "classification": classification,
                            "policy_excerpt": policy[:4000],
                            "user_intent_summary": enriched[:2000],
                        }
                    )
                )

            skeleton = await asyncio.to_thread(_draft)
            used = append_tool(state.get("used_tools"), "draft_response_tool")

            sys = SystemMessage(
                content=(
                    "You are a careful support writer for an AI learning platform. "
                    "Turn the internal skeleton and plan into a polished email-style reply. "
                    "Be warm, concise, and specific. Include timelines or policies only when grounded "
                    "in the provided policy text."
                )
            )
            human = HumanMessage(
                content=(
                    f"Internal skeleton:\n{skeleton}\n\n"
                    f"Planning notes:\n{plan[:4000]}\n\n"
                    f"Original learner/operator query:\n{state.get('user_query', '')}"
                )
            )
            resp = await ainvoke_with_retry(llm, [sys, human], request_id=rid or None)
            draft_reply = str(getattr(resp, "content", resp))

            sum_sys = SystemMessage(
                content=(
                    "Write a 2-3 sentence internal_summary for escalation: facts, category, "
                    "risk, and suggested owner team. Neutral tone."
                )
            )
            sum_h = HumanMessage(
                content=(
                    f"Classification: {classification}\n"
                    f"Query:\n{state.get('user_query', '')}\n"
                    f"Draft reply:\n{draft_reply[:3000]}"
                )
            )
            sum_resp = await ainvoke_with_retry(llm, [sum_sys, sum_h], request_id=rid or None)
            internal_summary = str(getattr(sum_resp, "content", sum_resp))

            return {
                "draft_reply": draft_reply,
                "internal_summary": internal_summary,
                "processing_notes": skeleton[:2000],
                "used_tools": used,
            }

    return respond_node
