"""Secrets loading: local .env vs AWS Secrets Manager."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Literal

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings, get_settings
from app.core.exceptions import SecretNotFoundError

logger = logging.getLogger(__name__)

SecretProviderType = Literal["env", "aws_secrets_manager"]


class SecretsProvider(ABC):
    """Abstract secrets access (never log secret values)."""

    @abstractmethod
    def get_openai_api_key(self) -> str:
        """Return OpenAI API key."""

    @property
    @abstractmethod
    def provider_type(self) -> SecretProviderType:
        """Identifier for observability (safe to expose)."""


class EnvSecretsProvider(SecretsProvider):
    """Load OPENAI_API_KEY from process environment."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def provider_type(self) -> SecretProviderType:
        return "env"

    def get_openai_api_key(self) -> str:
        import os

        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise SecretNotFoundError(
                "OPENAI_API_KEY is not set in environment for env-based secrets provider",
            )
        return key


class AwsSecretsManagerProvider(SecretsProvider):
    """Load secrets JSON from AWS Secrets Manager."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = boto3.client("secretsmanager", region_name=settings.aws_region)
        self._cached_key: str | None = None

    @property
    def provider_type(self) -> SecretProviderType:
        return "aws_secrets_manager"

    def get_openai_api_key(self) -> str:
        if self._cached_key is not None:
            return self._cached_key
        try:
            resp = self._client.get_secret_value(SecretId=self._settings.aws_secrets_manager_secret_name)
        except (ClientError, BotoCoreError) as exc:
            logger.error(
                "Failed to read secret from Secrets Manager",
                extra={
                    "secret_id": self._settings.aws_secrets_manager_secret_name,
                    "error_type": type(exc).__name__,
                },
            )
            raise SecretNotFoundError("Could not load secrets from AWS Secrets Manager") from exc

        payload: dict[str, Any]
        if "SecretString" in resp and resp["SecretString"]:
            raw = resp["SecretString"]
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                raise SecretNotFoundError("Secret payload is not valid JSON") from None
        else:
            raise SecretNotFoundError("Secret has no SecretString payload")

        key = str(payload.get("OPENAI_API_KEY", "")).strip()
        if not key:
            raise SecretNotFoundError("OPENAI_API_KEY missing in Secrets Manager JSON")
        self._cached_key = key
        return key


def build_secrets_provider(settings: Settings | None = None) -> SecretsProvider:
    """Factory for secrets provider based on configuration."""
    s = settings or get_settings()
    src = s.resolved_secrets_source
    if src == "env":
        return EnvSecretsProvider(s)
    return AwsSecretsManagerProvider(s)
