"""LangChain async callback: emit LangSmith-style run boundaries as structured JSON logs.

Those records follow the same path as other app logs (stdout, then optional watchtower
→ CloudWatch Logs). They are not a substitute for LangSmith’s hosted trace UI, but
they give you correlated ``run_id`` / parent spans and token usage in CloudWatch Logs
Insights.

Enable with ``ENABLE_LANGCHAIN_TRACE_LOGS=true`` (see ``Settings.enable_langchain_trace_logs``).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger("app.langchain_trace")


def _run_label(serialized: dict[str, Any]) -> str:
    return str(
        serialized.get("name")
        or serialized.get("id")
        or serialized.get("repr", "runnable")[:120]
    )


def _token_usage(response: LLMResult) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if response.llm_output and isinstance(response.llm_output, dict):
        tu = response.llm_output.get("token_usage") or response.llm_output.get("usage")
        if isinstance(tu, dict):
            out.update({str(k): v for k, v in tu.items()})
    return out


class LangChainTraceJsonLogger(AsyncCallbackHandler):
    """Per-request handler: logs chain / chat-model / tool spans with timing."""

    def __init__(self, *, request_id: str) -> None:
        super().__init__()
        self._request_id = request_id
        self._t0: dict[str, float] = {}

    def _mark_start(self, run_id: UUID) -> None:
        self._t0[str(run_id)] = time.monotonic()

    def _duration_ms(self, run_id: UUID) -> Optional[float]:
        t0 = self._t0.pop(str(run_id), None)
        if t0 is None:
            return None
        return round((time.monotonic() - t0) * 1000, 3)

    def _meta(
        self,
        trace_event: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        m: dict[str, Any] = {
            "trace_event": trace_event,
            "langchain_request_id": self._request_id,
            "run_id": str(run_id),
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
        }
        if extra:
            m.update(extra)
        return m

    async def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._mark_start(run_id)
        logger.info(
            "langchain_trace chain_start",
            extra={
                "safe_metadata": self._meta(
                    "chain_start",
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    extra={
                        "run_name": _run_label(serialized),
                        "tags": tags,
                        "langgraph_metadata": metadata,
                    },
                )
            },
        )

    async def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        ms = self._duration_ms(run_id)
        logger.info(
            "langchain_trace chain_end",
            extra={
                "duration_ms": ms,
                "safe_metadata": self._meta(
                    "chain_end",
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    extra={"output_keys": list(outputs.keys())[:20]},
                ),
            },
        )

    async def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        self._duration_ms(run_id)
        logger.error(
            "langchain_trace chain_error",
            extra={
                "safe_metadata": self._meta(
                    "chain_error",
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    extra={"error_type": type(error).__name__},
                )
            },
        )

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._mark_start(run_id)
        logger.info(
            "langchain_trace chat_model_start",
            extra={
                "safe_metadata": self._meta(
                    "chat_model_start",
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    extra={
                        "run_name": _run_label(serialized),
                        "message_batches": len(messages),
                    },
                )
            },
        )

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        ms = self._duration_ms(run_id)
        usage = _token_usage(response)
        logger.info(
            "langchain_trace llm_end",
            extra={
                "duration_ms": ms,
                "safe_metadata": self._meta(
                    "llm_end",
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    extra={"token_usage": usage},
                ),
            },
        )

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        self._duration_ms(run_id)
        logger.error(
            "langchain_trace llm_error",
            extra={
                "safe_metadata": self._meta(
                    "llm_error",
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    extra={"error_type": type(error).__name__},
                )
            },
        )

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        inputs: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._mark_start(run_id)
        snippet = input_str[:500] + ("…" if len(input_str) > 500 else "")
        logger.info(
            "langchain_trace tool_start",
            extra={
                "safe_metadata": self._meta(
                    "tool_start",
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    extra={"tool_name": _run_label(serialized), "input_preview": snippet},
                )
            },
        )

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        ms = self._duration_ms(run_id)
        out_preview = str(output)[:500] + ("…" if len(str(output)) > 500 else "")
        logger.info(
            "langchain_trace tool_end",
            extra={
                "duration_ms": ms,
                "safe_metadata": self._meta(
                    "tool_end",
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    extra={"output_preview": out_preview},
                ),
            },
        )

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        self._duration_ms(run_id)
        logger.error(
            "langchain_trace tool_error",
            extra={
                "safe_metadata": self._meta(
                    "tool_error",
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    extra={"error_type": type(error).__name__},
                )
            },
        )
