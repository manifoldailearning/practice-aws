"""LangChain ChatOpenAI factory; resilient async invoke."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings, get_settings


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


async def ainvoke_with_retry(llm: ChatOpenAI, messages: list[BaseMessage]) -> Any:
    """Invoke chat model with tenacity retries on transient failures."""

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.4, min=0.5, max=10),
        retry=retry_if_exception_type(_TransientLLMError),
    )
    async def _run() -> Any:
        try:
            return await llm.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001
            if _is_retryable(exc) or isinstance(exc, TimeoutError):
                raise _TransientLLMError(str(exc)) from exc
            raise

    return await _run()
