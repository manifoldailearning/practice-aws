"""LangChain tools for drafting support replies."""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def draft_response_tool(
    classification: str,
    policy_excerpt: str,
    user_intent_summary: str,
) -> str:
    """Produce a concise internal draft skeleton for a learner-facing reply.

    The LLM should polish this into final text. Include tone: professional, empathetic, clear next steps.
    """
    return (
        f"[Draft skeleton | classification={classification}]\n"
        f"Acknowledge the learner's situation regarding: {user_intent_summary}.\n"
        f"Ground in policy context:\n{policy_excerpt[:1200]}\n"
        "Offer clear next steps, timelines if applicable, and a single call-to-action."
    )
