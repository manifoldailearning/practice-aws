"""Prometheus metrics (HTTP counters/histogram). Logs remain on stdout / CloudWatch."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# Fixed route paths keep cardinality low for classroom clusters.
HTTP_REQUESTS = Counter(
    "support_ops_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "support_ops_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 120.0),
)

AGENT_INVOCATIONS = Counter(
    "support_ops_agent_invocations_total",
    "Agent graph invocations (respond + stream generators)",
    ["endpoint"],
)
