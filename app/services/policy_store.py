"""In-memory policy and curriculum store for the support ops demo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicySnippet:
    """Single retrievable policy excerpt."""

    topic: str
    content: str
    tags: tuple[str, ...]


# Realistic internal knowledge for an AI bootcamp / learning platform.
_POLICY_SNIPPETS: list[PolicySnippet] = [
    PolicySnippet(
        topic="Week 6 coverage",
        content=(
            "Week 6 focuses on agentic AI patterns: tool use, planning, evaluation, and "
            "production considerations including observability and guardrails. "
            "Learners build a small agent workflow and discuss enterprise tradeoffs."
        ),
        tags=("week6", "curriculum", "agents", "bootcamp"),
    ),
    PolicySnippet(
        topic="Cohort deferment",
        content=(
            "Deferment requests are reviewed within 2 business days. Learners may defer once "
            "to the next cohort if seats are available. Deferment must be requested before "
            "Week 4 live session. Confirm identity, cohort, and reason in writing. "
            "Escalate to Program Ops if payment or access anomalies are present."
        ),
        tags=("deferment", "policy", "cohort", "operations"),
    ),
    PolicySnippet(
        topic="Access and platform issues",
        content=(
            "For login or LMS access issues: verify email on account, password reset, and "
            "browser cache. Check SSO status if applicable. If still blocked, escalate "
            "with learner email and last error screenshot to Platform Support."
        ),
        tags=("access", "technical", "lms"),
    ),
    PolicySnippet(
        topic="Payments and invoices",
        content=(
            "Payment issues: confirm invoice ID, payment method, and any failed charge "
            "messages. Do not collect full card details in chat. Route to Billing for "
            "refunds or plan changes per finance policy."
        ),
        tags=("payment", "billing", "finance"),
    ),
    PolicySnippet(
        topic="Escalation paths",
        content=(
            "Escalate to Program Ops for deferment edge cases, cohort capacity, or conduct. "
            "Escalate to Engineering for reproducible bugs with steps to reproduce. "
            "Escalate to Billing for refunds and invoice disputes."
        ),
        tags=("escalation", "routing", "operations"),
    ),
]


class PolicyStore:
    """Simple keyword / tag search over static policy snippets."""

    def __init__(self, snippets: list[PolicySnippet] | None = None) -> None:
        self._snippets = snippets or list(_POLICY_SNIPPETS)

    def search(self, query: str, limit: int = 4) -> list[PolicySnippet]:
        """Rank snippets by crude token overlap with query."""
        q = query.lower()
        tokens = {t for t in q.replace("/", " ").split() if len(t) > 2}
        scored: list[tuple[float, PolicySnippet]] = []
        for s in self._snippets:
            hay = f"{s.topic} {s.content} {' '.join(s.tags)}".lower()
            score = sum(1 for t in tokens if t in hay)
            for tag in s.tags:
                if tag in q:
                    score += 2
            if score > 0:
                scored.append((float(score), s))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:limit]] if scored else list(self._snippets[:limit])
