"""Integration tests for HTTP API (mocked agent)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import clear_settings_cache
from app.main import app


class _FakeGraph:
    """Minimal async graph stub (matches LangGraph ainvoke/astream signatures)."""

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None, **_: Any
    ) -> dict[str, Any]:
        return {
            "classification": "deferment_request",
            "policy_context": "policy text",
            "recommended_action": "Confirm cohort and process deferment",
            "draft_reply": "Hello — we can help with deferment.",
            "internal_summary": "Deferment request; no billing flags.",
            "used_tools": ["classify_issue_tool", "search_bootcamp_policy_tool"],
        }

    async def astream(
        self,
        state: dict[str, Any],
        stream_mode: str | None = None,
        config: dict[str, Any] | None = None,
        **_: Any,
    ):
        yield {"classify": {"classification": "deferment_request"}}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Any:
    clear_settings_cache()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SECRETS_SOURCE", "env")
    with TestClient(app) as c:
        app.state.graph = _FakeGraph()
        yield c


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready(client: TestClient) -> None:
    r = client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True


def test_agent_respond_mocked(client: TestClient) -> None:
    payload = {
        "user_query": "A learner wants to defer to the next cohort because of timing issues.",
    }
    r = client.post("/agent/respond", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["classification"] == "deferment_request"
    assert "draft_reply" in data
    assert data["request_id"]


def test_golden_dataset_endpoint(client: TestClient) -> None:
    r = client.get("/demo/golden-dataset")
    assert r.status_code == 200
    body = r.json()
    assert body["version"]
    assert len(body["cases"]) >= 1
    assert body["cases"][0]["id"]


def test_prometheus_metrics_endpoint(client: TestClient) -> None:
    r = client.get("/metrics")
    assert r.status_code == 200
    text = r.text
    assert "support_ops_http_requests_total" in text
    assert "support_ops_http_request_duration_seconds" in text
