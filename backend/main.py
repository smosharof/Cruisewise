from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from backend.db import close_pool, init_pool
from backend.llm import configure_default_client
from backend.errors import CruisewiseError, NotFoundError, ValidationError
from backend.routers import account, booking, match, watch

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.configure_logging()
    logger.info("Starting Cruisewise (env=%s)", settings.app_env)

    # ADC lookup is fatal in production (Cloud Run metadata server should always
    # supply credentials) but degrades cleanly in development so the container
    # and /healthz still come up without a local gcloud auth setup.
    try:
        configure_default_client()
    except Exception as exc:
        if settings.is_production:
            raise
        logger.warning(
            "LLM client init failed (dev mode — continuing without LLM): %s", exc
        )

    try:
        await init_pool()
    except Exception as exc:
        # Same pattern: fatal in production, non-fatal in dev so the server still
        # boots and /healthz + stub endpoints remain reachable without Postgres.
        if settings.is_production:
            raise
        logger.warning("DB pool init failed (dev mode — continuing without DB): %s", exc)
    yield
    await close_pool()
    logger.info("Cruisewise shut down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Cruisewise",
        description="Match first-time cruisers to sailings. Watch booked sailings for reprice opportunities.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Domain error → HTTP mapping (one place, not scattered across routers) ---

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"ok": False, "error": str(exc)})

    @app.exception_handler(ValidationError)
    async def validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"ok": False, "error": str(exc)})

    @app.exception_handler(CruisewiseError)
    async def domain_error_handler(request: Request, exc: CruisewiseError) -> JSONResponse:
        logger.exception("Unhandled domain error")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})

    # --- Routers ---

    app.include_router(match.router, prefix="/api/match", tags=["match"])
    app.include_router(watch.router, prefix="/api/watch", tags=["watch"])
    app.include_router(booking.router, prefix="/api/booking", tags=["booking"])
    app.include_router(account.router, prefix="/api/account", tags=["account"])

    # --- Health ---
    # /healthz is reserved by Cloud Run's frontend (GFE intercepts and 404s
    # before requests reach the container). We keep /healthz for the local
    # TestClient suite where GFE isn't in the path, and expose /health as the
    # alias used by curl checks against the live service.

    async def _health_payload() -> dict:
        return {"status": "ok", "service": "cruisewise"}

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict:
        return await _health_payload()

    @app.get("/health", tags=["ops"])
    async def health() -> dict:
        return await _health_payload()

    # --- Static frontend (serve in prod; in dev, open index.html directly) ---
    try:
        app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
    except RuntimeError:
        # frontend/ doesn't exist during testing
        pass

    return app


app = create_app()
