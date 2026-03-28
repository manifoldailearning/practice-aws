"""Unit tests for LangChain tools."""

from __future__ import annotations

from app.tools.classification_tools import classify_issue_tool
from app.tools.policy_tools import search_bootcamp_policy_tool


def test_classify_issue_tool_defers() -> None:
    out = classify_issue_tool.invoke({"message": "I need to defer to the next cohort due to timing"})
    assert "deferment" in out.lower()


def test_policy_search_week6() -> None:
    out = search_bootcamp_policy_tool.invoke({"query": "What is covered in Week 6?"})
    assert "Week 6" in out or "week 6" in out.lower()
