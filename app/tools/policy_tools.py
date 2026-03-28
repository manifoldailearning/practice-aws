"""LangChain tools for bootcamp policy lookup."""

from __future__ import annotations

from langchain_core.tools import tool

from app.services.policy_store import PolicyStore

_store = PolicyStore()


@tool
def search_bootcamp_policy_tool(query: str) -> str:
    """Search internal bootcamp policy and curriculum snippets by topic or keywords.

    Use for questions about weeks, cohort rules, deferments, access, billing, or escalation.
    Pass a short natural-language query describing what to look up.
    """
    hits = _store.search(query, limit=4)
    if not hits:
        return "No matching policy snippets found."
    lines: list[str] = []
    for h in hits:
        lines.append(f"### {h.topic}\n{h.content}\n(tags: {', '.join(h.tags)})")
    return "\n\n".join(lines)
