"""Demo scenario resolution for policy lookup."""

from __future__ import annotations

import pytest

from app.core.config import Settings, clear_settings_cache
from app.core.demo_scenarios import resolve_demo_policy_lookup


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_demo_disabled_returns_none() -> None:
    s = Settings(enable_demo_scenarios=False)
    assert resolve_demo_policy_lookup("[demo:tool-failure] x", s) == "none"


def test_failure_wins_over_slow() -> None:
    s = Settings(enable_demo_scenarios=True)
    q = "help [demo:tool-failure] and [demo:slow-tool]"
    assert resolve_demo_policy_lookup(q, s) == "failure"


def test_slow_when_configured() -> None:
    s = Settings(enable_demo_scenarios=True)
    assert resolve_demo_policy_lookup("Please [demo:slow-tool] thanks", s) == "slow"


def test_case_insensitive() -> None:
    s = Settings(enable_demo_scenarios=True)
    assert resolve_demo_policy_lookup("X [DEMO:TOOL-FAILURE] y", s) == "failure"
