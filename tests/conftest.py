"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from app.core.config import clear_settings_cache


@pytest.fixture(autouse=True)
def _env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_cache()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("SECRETS_SOURCE", "env")
    monkeypatch.setenv("ENVIRONMENT", "test")
    yield
    clear_settings_cache()
