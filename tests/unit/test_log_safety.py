"""Unit tests for log truncation."""

from __future__ import annotations

from app.core.log_safety import truncate_for_log


def test_truncate_for_log_short() -> None:
    assert truncate_for_log("hello", 100) == "hello"


def test_truncate_for_log_long() -> None:
    s = "a" * 100
    out = truncate_for_log(s, 10)
    assert len(out) == 10
    assert out.endswith("…")
