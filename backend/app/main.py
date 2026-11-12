import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.api.v1 import auth, chat, compare, dashboard, health, providers
from app.core.config import Settings, get_settings
from app.core.database import lifespan_mongo
from app.core.middleware import RateLimiter, SecurityMiddleware
from app.services.ai.base_provider import ProviderError

logger = logging.getLogger(__name__)

def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        async with lifespan_mongo(settings) as client:
            _app.state.mongo_client = client
            yield

    application = FastAPI(
        title="AI Knowledge Hub API",
        version="0.1.0",
        description="Phase 1: authentication, database readiness, and user dashboard.",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.rate_limiter = RateLimiter(settings)
    application.add_middleware(
        SecurityMiddleware, settings=settings, limiter=application.state.rate_limiter
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    @application.exception_handler(ProviderError)
    async def provider_error(_request: Request, exc: ProviderError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        if _request.url.path.startswith("/api/v1/ai"):
            # Never echo submitted keys, passwords, extra field names or parser context.
            error = ProviderError("invalid_provider_configuration")
            return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
        # Pydantic's default input/ctx fields can echo submitted passwords.
        errors = [
            {"type": error["type"], "loc": list(error["loc"]), "msg": error["msg"]}
            for error in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": errors})

    @application.exception_handler(PyMongoError)
    async def database_error(_request: Request, exc: PyMongoError):
        logger.error("Database request failed (%s)", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "Database unavailable"})

    @application.exception_handler(Exception)
    async def unexpected_error(_request: Request, exc: Exception):
        logger.error("Request failed (%s)", type(exc).__name__)
        if _request.url.path.startswith("/api/v1/ai"):
            return JSONResponse(
                status_code=500,
                content={
                    "detail": {"code": "internal_server_error", "message": "Internal server error."}
                },
                headers={"Cache-Control": "no-store"},
            )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    for router in (
        health.router,
        auth.router,
        dashboard.router,
        providers.router,
        chat.router,
        compare.router,
    ):
        application.include_router(router, prefix="/api/v1")
    return application


app = create_app()