"""FastAPI entrypoint for the media-content-insight backend.

This module wires up the bare-minimum scaffold that subsequent tasks build on:

* a placeholder health-check route at ``/`` (no domain routers are mounted
  yet -- those land in tasks 5.x and 6.x);
* CORS restricted to loopback origins so that the API can never be invoked
  from a non-local browser context (requirement 19.11);
* lifespan hooks reserved for database initialisation (filled in by task
  2.1) and graceful shutdown;
* a unified exception handler that always returns
  ``{"code", "message", "detail"}`` regardless of which exception type was
  raised (HTTPException, validation errors, or any unexpected exception);
* a ``__main__`` block that defaults uvicorn to ``settings.HOST``
  (``127.0.0.1``) so accidental ``python -m app.main`` invocations stay
  inside the compliance baseline.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.db import dispose_engine, init_db
from app.core.logger import logger

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup / shutdown hook.

    The startup branch initialises the SQLite database (creates the file
    under ``data/`` if missing and runs ``Base.metadata.create_all``
    with ``PRAGMA foreign_keys=ON`` enabled). The shutdown branch
    disposes the async engine to release the connection cleanly.
    """
    logger.info(
        "backend startup",
        extra={
            "event": "startup",
            "host": settings.HOST,
            "port": settings.PORT,
            "settings": settings.to_safe_dict(),
        },
    )
    await init_db()
    try:
        yield
    finally:
        await dispose_engine()
        logger.info("backend shutdown", extra={"event": "shutdown"})


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _error_payload(code: Any, message: str, detail: Any = None) -> dict[str, Any]:
    """Build the canonical error response body.

    The triple ``{"code", "message", "detail"}`` is mandated by the
    project-wide error contract (see ``requirements.md`` 备注 section).
    """
    return {"code": code, "message": message, "detail": detail}


def create_app() -> FastAPI:
    """Construct and return the FastAPI application.

    Kept as a factory so that tests can build isolated app instances.
    """
    app = FastAPI(
        title="media-content-insight backend",
        version="0.1.0",
        description=(
            "Local, single-user, research-only multi-platform content insight "
            "MVP backend. See docs/compliance.md for the full compliance "
            "baseline."
        ),
        lifespan=lifespan,
    )

    # Restrict CORS to loopback origins. The frontend dev server (Vite)
    # listens on 5173 by default; CRA / other tooling on 3000 is included
    # for convenience. Crucially, no non-loopback origin is ever allowed,
    # which together with ``HOST=127.0.0.1`` enforces requirement 19.11.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_origin_regex=settings.cors_allow_origin_regex,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    _register_exception_handlers(app)
    _register_placeholder_routes(app)

    return app


def _register_placeholder_routes(app: FastAPI) -> None:
    """Register the health probe plus any already-implemented routers.

    Domain routers are mounted here as their owning tasks land. Each
    router contributes a slice of the 9-endpoint public API surface
    locked down by requirement 19.1; *adding* a router here without a
    matching route in :doc:`requirements.md` 19.1 would silently widen
    that contract, so every addition must be cross-checked against
    the requirement document.

    Currently mounted:

    * health probe at ``/`` (always on);
    * ``app.api.tasks`` -- ``POST /api/tasks`` (task 5.1). The same
      router will pick up ``GET /api/tasks``, ``GET
      /api/tasks/{id}``, ``GET /api/tasks/{id}/export`` as tasks
      5.3 / 5.4 / 5.5 land.
    * ``app.api.notes`` -- ``GET /api/tasks/{task_id}/notes``
      (task 6.1). ``GET /api/notes/{note_id}`` (task 6.2) joins this
      router later.
    * ``app.api.comments`` -- ``GET /api/tasks/{task_id}/comments``
      (task 6.3): aggregates a task's comments into top keywords,
      a three-way sentiment distribution, and the top hot
      comments. The aggregation is rule-based MVP; the wire shape
      is locked down by :mod:`app.schemas.comment` so a future
      swap to ``jieba`` + a real model will not change the API
      contract.
    """

    @app.get("/", tags=["health"], summary="Liveness probe")
    async def root() -> dict[str, str]:
        """Return a small JSON document confirming the service is up."""
        return {"status": "ok", "service": "media-content-insight"}

    # Import lazily so a circular-import bug in any router module
    # (or a future dependency that calls ``create_app()`` to peek at
    # the schema) cannot wedge the application package itself.
    from app.api.ai_reports import router as ai_reports_router
    from app.api.comments import router as comments_router
    from app.api.notes import router as notes_router
    from app.api.tasks import router as tasks_router

    app.include_router(tasks_router)
    app.include_router(notes_router)
    app.include_router(comments_router)
    app.include_router(ai_reports_router)


def _register_exception_handlers(app: FastAPI) -> None:
    """Wire up the unified ``{code, message, detail}`` error contract."""

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        # ``HTTPException(status_code=..., detail=...)`` is the conventional
        # way for handlers to surface domain-specific error codes. We
        # interpret ``detail`` either as a structured payload (dict with
        # ``code``/``message``/``detail`` keys) or as a plain string.
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            payload = _error_payload(
                code=detail.get("code"),
                message=str(detail.get("message", "")),
                detail=detail.get("detail"),
            )
        else:
            payload = _error_payload(
                code=exc.status_code,
                message=str(detail) if detail is not None else "HTTP error",
                detail=None,
            )
        logger.warning(
            "http error",
            extra={
                "event": "http_error",
                "path": request.url.path,
                "method": request.method,
                "status_code": exc.status_code,
                "code": payload["code"],
            },
        )
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # 422 is the standard FastAPI / Starlette validation status code.
        payload = _error_payload(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            detail=exc.errors(),
        )
        logger.warning(
            "validation error",
            extra={
                "event": "validation_error",
                "path": request.url.path,
                "method": request.method,
            },
        )
        return JSONResponse(status_code=422, content=payload)

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        # Anything that escapes the handlers above is treated as an
        # internal error. We log with traceback context but never leak the
        # raw exception message to the client.
        logger.exception(
            "unhandled exception",
            extra={
                "event": "internal_error",
                "path": request.url.path,
                "method": request.method,
            },
        )
        payload = _error_payload(
            code="INTERNAL_ERROR",
            message="Internal server error",
            detail=None,
        )
        return JSONResponse(status_code=500, content=payload)


# Module-level app for ``uvicorn app.main:app``.
app: FastAPI = create_app()


# ---------------------------------------------------------------------------
# Entrypoint for ``python -m app.main``
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover - exercised manually
    import uvicorn

    # Default uvicorn binding to settings.HOST (127.0.0.1) so accidental
    # ``python -m app.main`` invocations stay within the compliance baseline.
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
    )
