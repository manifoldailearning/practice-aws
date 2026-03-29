"""Truncate potentially large or sensitive text for structured logs (stdout / CloudWatch)."""

from __future__ import annotations

_ELLIPSIS = "…"


def truncate_for_log(text: str, max_chars: int) -> str:
    """Return ``text`` capped at ``max_chars`` with an ellipsis suffix when truncated."""
    if max_chars <= 0:
        return ""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= len(_ELLIPSIS):
        return text[:max_chars]
    return text[: max_chars - len(_ELLIPSIS)] + _ELLIPSIS
