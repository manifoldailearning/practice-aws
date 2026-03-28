"""Response planning node — next best action and plan for the reply."""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agents.node_utils import node_span
from app.agents.state import AgentState
from app.core.llm import ainvoke_with_retry

logger = logging.getLogger(__name__)


def build_plan_node(llm: ChatOpenAI):
    """Factory for planning node."""

    async def plan_node(state: AgentState) -> AgentState:
        rid = state.get("request_id", "")
        with node_span(logger, "plan", rid):
            classification = state.get("classification", "")
            policy = state.get("policy_context", "")
            enriched = state.get("enriched_context", "")
            sys = SystemMessage(
                content=(
                    "You are a senior support operations lead. Produce:\n"
                    "1) A one-line recommended_action for the support agent.\n"
                    "2) A short numbered plan (3-5 bullets) for the learner-facing reply.\n"
                    "Format exactly as:\n"
                    "RECOMMENDED_ACTION: ...\n"
                    "PLAN:\n- ...\n- ...\n"
                )
            )
            human = HumanMessage(
                content=(
                    f"Classification: {classification}\n"
                    f"Enriched context:\n{enriched}\n"
                    f"Policy excerpts:\n{policy[:6000]}"
                )
            )
            resp = await ainvoke_with_retry(llm, [sys, human])
            text = str(getattr(resp, "content", resp))
            recommended = ""
            for line in text.splitlines():
                if line.strip().upper().startswith("RECOMMENDED_ACTION:"):
                    recommended = line.split(":", 1)[1].strip()
                    break
            if not recommended:
                recommended = "Confirm details with learner; follow policy excerpts and escalate if needed."
            return {
                "plan": text,
                "recommended_action": recommended,
            }

    return plan_node
