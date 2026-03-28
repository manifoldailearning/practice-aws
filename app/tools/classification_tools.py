"""LangChain tools for issue classification."""

from __future__ import annotations

from typing import Literal

from langchain_core.tools import tool

IssueKind = Literal["access_issue", "payment_issue", "deferment_request", "technical_issue", "general_support"]


_KEYWORDS: dict[IssueKind, tuple[str, ...]] = {
    "access_issue": ("login", "password", "locked", "access", "sso", "cannot log", "locked out"),
    "payment_issue": ("invoice", "charge", "payment", "refund", "billing", "card", "paid"),
    "deferment_request": ("defer", "next cohort", "postpone", "delay", "timing", "schedule"),
    "technical_issue": ("bug", "error", "crash", "timeout", "broken", "not loading", "500"),
    "general_support": ("question", "help", "how do i", "where", "when"),
}


def _classify_heuristic(text: str) -> IssueKind:
    lower = text.lower()
    scores: dict[IssueKind, int] = {k: 0 for k in _KEYWORDS}
    for kind, words in _KEYWORDS.items():
        scores[kind] = sum(1 for w in words if w in lower)
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return "general_support"
    return best


@tool
def classify_issue_tool(message: str) -> str:
    """Classify a learner or support message into a support category.

    Returns one of: access_issue, payment_issue, deferment_request, technical_issue, general_support.
    """
    kind = _classify_heuristic(message)
    return f"{kind}"


def classify_issue_direct(message: str) -> IssueKind:
    """Programmatic classification (used by graph without extra LLM)."""
    return _classify_heuristic(message)
