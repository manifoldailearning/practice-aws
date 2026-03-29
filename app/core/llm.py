"""LangChain ChatOpenAI factory; resilient async invoke."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings, get_settings
from app.core.log_safety import truncate_for_log
from app.services.request_context import get_request_context

logger = logging.getLogger(__name__)


class _TransientLLMError(Exception):
    """Retryable OpenAI / network failures."""


def build_chat_model(*, api_key: str, settings: Settings | None = None) -> ChatOpenAI:
    """Construct a configured ChatOpenAI client."""
    s = settings or get_settings()
    return ChatOpenAI(
        model=s.openai_model,
        api_key=api_key,
        timeout=s.request_timeout_seconds,
        max_retries=0,
    )


def _response_content_preview(result: Any, max_chars: int) -> str:
    """Extract text from an AIMessage / object for logs."""
    content = getattr(result, "content", None)
    if content is None:
        return truncate_for_log(str(result), max_chars)
    if isinstance(content, str):
        return truncate_for_log(content, max_chars)
    return truncate_for_log(str(content), max_chars)


def _log_llm_completion(result: Any, *, request_id: str | None = None) -> None:
    settings = get_settings()
    cap = settings.agent_io_log_max_chars
    if cap <= 0:
        return
    ctx = get_request_context()
    rid = request_id or (ctx.request_id if ctx else None)
    preview = _response_content_preview(result, cap)
    logger.info(
        "LLM response",
        extra={
            "log_event": "llm_response",
            "safe_metadata": {
                "request_id": rid,
                "response_preview": preview,
                "model": settings.openai_model,
            },
        },
    )


def _is_retryable(exc: BaseException) -> bool:
    name = type(exc).__name__
    markers = (
        "Timeout",
        "APIConnectionError",
        "APITimeoutError",
        "RateLimitError",
        "InternalServerError",
        "ConnectError",
    )
    return any(x in name for x in markers)


async def ainvoke_with_retry(
    llm: ChatOpenAI,
    messages: list[BaseMessage],
    *,
    request_id: str | None = None,
) -> Any:
    """Invoke chat model with tenacity retries on transient failures.

    Pass ``request_id`` from graph state so LLM logs correlate during SSE streams
    (HTTP context may be cleared before the graph runs).
    """

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.4, min=0.5, max=10),
        retry=retry_if_exception_type(_TransientLLMError),
    )
    async def _run() -> Any:
        try:
            out = await llm.ainvoke(messages)
            _log_llm_completion(out, request_id=request_id)
            return out
        except Exception as exc:  # noqa: BLE001
            if _is_retryable(exc) or isinstance(exc, TimeoutError):
                raise _TransientLLMError(str(exc)) from exc
            raise

    return await _run()
