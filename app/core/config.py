"""Application configuration via pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="support-ops-agent", description="Service display name")
    environment: str = Field(default="development", description="deployment environment name")
    log_level: str = Field(default="INFO", description="Root log level")

    openai_model: str = Field(default="gpt-4.1-nano", description="Default OpenAI chat model")
    aws_region: str = Field(default="us-east-1", description="AWS region for SDK clients")
    aws_secrets_manager_secret_name: str = Field(
        default="support-ops-agent/openai",
        description="Secrets Manager secret name or ARN prefix",
    )
    cloudwatch_log_group: str = Field(
        default="/support-ops/agent",
        description="CloudWatch Logs group when direct handler is enabled",
    )
    cloudwatch_log_stream_prefix: str = Field(
        default="agent",
        description="Prefix-safe stream name segment for log streams",
    )
    enable_cloudwatch_logging: bool = Field(
        default=False,
        description="If true, also emit logs to CloudWatch via watchtower",
    )
    enable_langchain_trace_logs: bool = Field(
        default=False,
        description="If true, attach LangChain trace callback (structured logs → stdout / CloudWatch)",
    )
    redis_url: str | None = Field(default=None, description="Optional Redis URL for future cache")
    request_timeout_seconds: float = Field(default=120.0, description="Upstream request timeout")

    agent_io_log_max_chars: int = Field(
        default=4000,
        ge=0,
        description="Max characters per logged field (user query, LLM text, draft reply) for troubleshooting",
    )

    enable_demo_scenarios: bool = Field(
        default=False,
        description="If true, allow demo substrings in user_query to simulate policy tool failure or delay",
    )
    demo_tool_failure_substring: str = Field(
        default="[demo:tool-failure]",
        description="If present in user_query (case-insensitive), policy_lookup raises after logging",
    )
    demo_slow_tool_substring: str = Field(
        default="[demo:slow-tool]",
        description="If present in user_query (case-insensitive), policy_lookup sleeps before the tool runs",
    )
    demo_slow_tool_delay_seconds: float = Field(
        default=12.0,
        ge=0.0,
        le=120.0,
        description="Sleep duration for slow-tool demo (capped for safety)",
    )

    secrets_source: Literal["auto", "env", "aws_secrets_manager"] = Field(
        default="auto",
        description="Where to load OPENAI_API_KEY from",
    )

    @property
    def resolved_secrets_source(self) -> Literal["env", "aws_secrets_manager"]:
        """Resolve auto mode based on environment."""
        if self.secrets_source != "auto":
            return self.secrets_source
        if self.environment.lower() in {"production", "staging"}:
            return "aws_secrets_manager"
        return "env"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear settings cache (used in tests)."""
    get_settings.cache_clear()
