"""Unit tests for configuration."""

from __future__ import annotations

import pytest

from app.core.config import Settings, clear_settings_cache, get_settings


def test_settings_loads_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_cache()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("SECRETS_SOURCE", "env")
    s = Settings()
    assert s.openai_model == "gpt-4.1-nano"
    assert s.environment


def test_resolved_secrets_source_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_cache()
    monkeypatch.setenv("SECRETS_SOURCE", "auto")
    monkeypatch.setenv("ENVIRONMENT", "production")
    s = Settings()
    assert s.resolved_secrets_source == "aws_secrets_manager"


def test_get_settings_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_cache()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    a = get_settings()
    b = get_settings()
    assert a is b
