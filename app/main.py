"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import __version__
from app.api.middleware import RequestContextMiddleware
from app.api.routes import router
from app.core.config import get_settings
from app.core.exceptions import AppException, AgentInvocationError, error_payload
from app.core.logging import setup_logging
from app.core.metrics import REGISTRY, monotonic_ms
from app.core.llm import build_chat_model
from app.core.secrets import SecretsProvider, build_secrets_provider
from app.agents.graph import build_support_graph
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load secrets, compile graph, attach shared state."""
    settings = get_settings()
    setup_logging(settings)

    try:
        secrets_provider: SecretsProvider = build_secrets_provider(settings)
        api_key = secrets_provider.get_openai_api_key()
    except Exception as exc:  # noqa: BLE001
        logger.error("Startup failed: secrets", extra={"error_type": type(exc).__name__})
        raise

    llm = build_chat_model(api_key=api_key, settings=settings)
    graph = build_support_graph(llm)

    app.state.secrets_provider = secrets_provider
    app.state.llm = llm
    app.state.graph = graph
    app.state.settings = settings

    logger.info(
        "Application startup complete",
        extra={"safe_metadata": {"version": __version__, "model": settings.openai_model}},
    )
    yield
    logger.info("Application shutdown")


def create_app() -> FastAPI:
    """Application factory for tests and uvicorn."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start = monotonic_ms()
        try:
            response = await call_next(request)
            success = response.status_code < 400
        except Exception:
            REGISTRY.record_request(success=False, latency_ms=monotonic_ms() - start)
            raise
        REGISTRY.record_request(success=success, latency_ms=monotonic_ms() - start)
        return response

    app.add_middleware(RequestContextMiddleware)
    app.include_router(router)

    @app.exception_handler(AppException)
    async def _app_exception_handler(request: Request, exc: AppException):
        from app.services.request_context import get_request_context

        ctx = get_request_context()
        rid = ctx.request_id if ctx else None
        if isinstance(exc, AgentInvocationError):
            status = 500
        elif exc.code == "secret_not_found":
            status = 503
        elif exc.code == "configuration_error":
            status = 503
        else:
            status = 400
        return JSONResponse(
            status_code=status,
            content=error_payload(message=exc.message, code=exc.code, request_id=rid),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        from app.services.request_context import get_request_context

        ctx = get_request_context()
        rid = ctx.request_id if ctx else None
        return JSONResponse(
            status_code=422,
            content=error_payload(
                message="Validation error",
                code="validation_error",
                request_id=rid,
                details={"errors": exc.errors()},
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        from app.services.request_context import get_request_context

        ctx = get_request_context()
        rid = ctx.request_id if ctx else None
        logger.exception("Unhandled error", extra={"request_id": rid})
        return JSONResponse(
            status_code=500,
            content=error_payload(
                message="Internal server error",
                code="internal_error",
                request_id=rid,
            ),
        )

    return app


app = create_app()
