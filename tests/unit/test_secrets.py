"""Unit tests for secrets providers."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.exceptions import SecretNotFoundError
from app.core.secrets import AwsSecretsManagerProvider, EnvSecretsProvider


def test_env_provider_reads_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    s = Settings()
    p = EnvSecretsProvider(s)
    assert p.get_openai_api_key() == "sk-secret"
    assert p.provider_type == "env"


def test_env_provider_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    s = Settings()
    p = EnvSecretsProvider(s)
    with pytest.raises(SecretNotFoundError):
        p.get_openai_api_key()


def test_aws_provider_parses_json(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings(aws_region="us-east-1", aws_secrets_manager_secret_name="dummy")

    class FakeClient:
        def get_secret_value(self, SecretId: str):  # noqa: N803
            return {"SecretString": '{"OPENAI_API_KEY": "sk-aws"}'}

    monkeypatch.setattr(
        "app.core.secrets.boto3.client",
        lambda service, region_name=None: FakeClient(),
    )
    p = AwsSecretsManagerProvider(s)
    assert p.get_openai_api_key() == "sk-aws"
    assert p.provider_type == "aws_secrets_manager"
