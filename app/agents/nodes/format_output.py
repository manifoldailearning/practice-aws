"""Final formatting node — guardrail-style validation and stable output fields."""

from __future__ import annotations

import logging

from app.agents.node_utils import node_span
from app.agents.state import AgentState

logger = logging.getLogger(__name__)


def build_format_output_node():
    """Factory for formatting / validation node."""

    async def format_output_node(state: AgentState) -> AgentState:
        rid = state.get("request_id", "")
        with node_span(logger, "format_output", rid):
            draft = (state.get("draft_reply") or "").strip()
            if len(draft) > 12000:
                draft = draft[:12000] + "\n\n[truncated]"
            notes = state.get("processing_notes", "")
            if "password" in notes.lower() and "reset" not in draft.lower():
                draft = (
                    draft
                    + "\n\n(Internal note: verify whether a password reset was suggested if access-related.)"
                )
            return {
                "draft_reply": draft,
                "processing_notes": notes,
            }

    return format_output_node
