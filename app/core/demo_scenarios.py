"""Optional classroom triggers for policy lookup (failure + artificial delay).

Disabled unless ``enable_demo_scenarios`` is true. Triggers are substrings in ``user_query``.
"""

from __future__ import annotations

from typing import Literal

from app.core.config import Settings

DemoPolicyLookup = Literal["none", "failure", "slow"]


def resolve_demo_policy_lookup(user_query: str, settings: Settings) -> DemoPolicyLookup:
    """Return which demo branch applies before ``search_bootcamp_policy_tool`` runs."""
    if not settings.enable_demo_scenarios:
        return "none"
    q = user_query.lower()
    fail = (settings.demo_tool_failure_substring or "").lower()
    slow = (settings.demo_slow_tool_substring or "").lower()
    if fail and fail in q:
        return "failure"
    if slow and slow in q:
        return "slow"
    return "none"
