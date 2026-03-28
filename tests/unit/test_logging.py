"""Logging setup tests."""

from __future__ import annotations

from app.core.config import Settings
from app.core.logging import reset_logging_for_tests, setup_logging


def test_setup_logging_stdout_without_cloudwatch() -> None:
    reset_logging_for_tests()
    s = Settings(enable_cloudwatch_logging=False, log_level="INFO")
    setup_logging(s)
    reset_logging_for_tests()
