"""Lightweight in-process metrics for demos and basic observability."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class MetricsRegistry:
    """Thread-safe counters and latency average (Welford-style for mean)."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    agent_invocation_count: int = 0
    _latency_sum_ms: float = 0.0
    _latency_n: int = 0

    def record_request(self, *, success: bool, latency_ms: float) -> None:
        with self._lock:
            self.request_count += 1
            if success:
                self.success_count += 1
            else:
                self.failure_count += 1
            self._latency_sum_ms += latency_ms
            self._latency_n += 1

    def record_agent_invocation(self) -> None:
        with self._lock:
            self.agent_invocation_count += 1

    def summary(self) -> dict[str, float | int]:
        with self._lock:
            avg = (
                self._latency_sum_ms / self._latency_n
                if self._latency_n
                else 0.0
            )
            return {
                "request_count": self.request_count,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "average_latency_ms": round(avg, 3),
                "agent_invocation_count": self.agent_invocation_count,
            }


REGISTRY = MetricsRegistry()


def monotonic_ms() -> float:
    """Monotonic time in milliseconds."""
    return time.perf_counter() * 1000.0
