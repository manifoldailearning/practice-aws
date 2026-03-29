"""Golden-set regression: POST /agent/respond and assert classification matches expected.

Uses a graph stub that returns ``expected_classification`` for each known ``user_query``,
so the suite is deterministic and safe for CI and classroom demos. It demonstrates the
*shape* of LLM regression tests; a separate live-LLM eval would be flaky unless you
freeze outputs or use thresholds."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import clear_settings_cache
from app.core.golden_dataset import GoldenCase, load_golden_dataset
from app.main import app


class _GoldenRegressionGraph:
    """Stub graph: looks up ``user_query`` in the golden file and returns that label."""

    def __init__(self) -> None:
        ds = load_golden_dataset()
        self._by_query: dict[str, GoldenCase] = {c.user_query: c for c in ds.cases}

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None, **_: Any
    ) -> dict[str, Any]:
        q = str(state.get("user_query") or "")
        case = self._by_query.get(q)
        if case is None:
            raise RuntimeError(
                "No golden row for this user_query — add it to data/golden_dataset.json"
            )
        label = case.expected_classification
        return {
            "classification": label,
            "policy_context": f"(stub) policy context for {case.id}",
            "recommended_action": f"(stub) action for {label}",
            "draft_reply": f"(stub) draft for {case.id}",
            "internal_summary": f"(stub) summary for {case.id}",
            "used_tools": ["classify_issue_tool"],
        }

    async def astream(
        self,
        state: dict[str, Any],
        stream_mode: str | None = None,
        config: dict[str, Any] | None = None,
        **_: Any,
    ):
        q = str(state.get("user_query") or "")
        case = self._by_query.get(q)
        label = case.expected_classification if case else "unknown"
        yield {"classify": {"classification": label}}


@pytest.fixture
def golden_regression_client(monkeypatch: pytest.MonkeyPatch) -> Any:
    clear_settings_cache()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SECRETS_SOURCE", "env")
    with TestClient(app) as client:
        app.state.graph = _GoldenRegressionGraph()
        yield client


def _golden_cases() -> list[GoldenCase]:
    return load_golden_dataset().cases


@pytest.mark.parametrize("case", _golden_cases(), ids=lambda c: c.id)
def test_golden_classification_regression(
    golden_regression_client: TestClient, case: GoldenCase
) -> None:
    """Each golden row: API response classification must match expected."""
    r = golden_regression_client.post(
        "/agent/respond",
        json={"user_query": case.user_query},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["classification"] == case.expected_classification, (
        f"case {case.id}: got {body['classification']!r}, want {case.expected_classification!r}"
    )
