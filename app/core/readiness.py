"""Readiness checks for Kubernetes / load balancers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from app.core.config import Settings, get_settings
from app.core.secrets import SecretsProvider, build_secrets_provider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReadinessResult:
    """Outcome of readiness probe (no secrets exposed)."""

    ready: bool
    checks: dict[str, str]

    def to_public_dict(self) -> dict[str, Any]:
        return {"ready": self.ready, "checks": self.checks}


class ReadinessService:
    """Validates configuration and ability to load required secrets."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def check(self, secrets: SecretsProvider | None = None) -> ReadinessResult:
        checks: dict[str, str] = {}
        ok = True

        if not self._settings.app_name:
            ok = False
            checks["config"] = "invalid: app_name"
        else:
            checks["config"] = "ok"

        prov = secrets or build_secrets_provider(self._settings)
        try:
            _ = prov.get_openai_api_key()
            checks["secrets"] = "ok"
        except Exception as exc:  # noqa: BLE001
            ok = False
            checks["secrets"] = f"unavailable: {type(exc).__name__}"
            logger.warning("Readiness: secrets check failed", extra={"error_type": type(exc).__name__})

        if self._settings.redis_url:
            parsed = urlparse(self._settings.redis_url)
            if not parsed.scheme or not parsed.hostname:
                ok = False
                checks["redis"] = "invalid_url"
            else:
                checks["redis"] = "configured_not_verified"

        return ReadinessResult(ready=ok, checks=checks)
