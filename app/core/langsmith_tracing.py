"""RunnableConfig helpers for LangSmith (LangChain tracing).

LangChain/LangGraph send traces to LangSmith when process env is set, for example:
  LANGCHAIN_TRACING_V2=true
  LANGCHAIN_API_KEY=ls__...
  LANGCHAIN_PROJECT=support-ops-agent

Alternatively LANGSMITH_API_KEY is recognized by newer clients. Passing ``metadata``
and ``tags`` on each graph run improves filtering in the LangSmith UI.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.core.config import get_settings
from app.core.trace_logging_callback import LangChainTraceJsonLogger


def graph_run_config(*, request_id: str, environment: str, endpoint: str) -> RunnableConfig:
    """Config for ``graph.ainvoke`` / ``graph.astream``.

    - LangSmith: set ``LANGCHAIN_TRACING_V2`` + API key; ``metadata`` / ``tags`` help filter runs.
    - CloudWatch: set ``ENABLE_LANGCHAIN_TRACE_LOGS=true`` to emit span-style JSON logs (same
      pipeline as other logs: stdout → cluster log shipper, or watchtower when enabled).
    """
    short_rid = request_id[:16] if len(request_id) > 16 else request_id
    cfg: RunnableConfig = {
        "run_name": f"support_ops_{short_rid}",
        "metadata": {
            "request_id": request_id,
            "environment": environment,
            "endpoint": endpoint,
        },
        "tags": [environment, "support-ops-agent"],
    }
    if get_settings().enable_langchain_trace_logs:
        cfg["callbacks"] = [LangChainTraceJsonLogger(request_id=request_id)]
    return cfg
