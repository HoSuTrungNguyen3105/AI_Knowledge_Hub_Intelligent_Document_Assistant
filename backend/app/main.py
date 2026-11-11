import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1 import auth, dashboard, health
from app.core.config import Settings, get_settings
from app.core.database import build_engine, build_session_factory
from app.core.middleware import RateLimiter, SecurityMiddleware

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = build_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        engine.dispose()

    application = FastAPI(
        title="AI Knowledge Hub API",
        version="0.1.0",
        description="Phase 1: authentication, database readiness, and user dashboard.",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.engine = engine
    application.state.session_factory = build_session_factory(engine)
    application.state.rate_limiter = RateLimiter(settings)
    application.add_middleware(
        SecurityMiddleware, settings=settings, limiter=application.state.rate_limiter
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        # Pydantic's default input/ctx fields can echo submitted passwords.
        errors = [
            {"type": error["type"], "loc": list(error["loc"]), "msg": error["msg"]}
            for error in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": errors})

    @application.exception_handler(SQLAlchemyError)
    async def database_error(_request: Request, exc: SQLAlchemyError):
        logger.error("Database request failed (%s)", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "Database unavailable"})

    @application.exception_handler(Exception)
    async def unexpected_error(_request: Request, exc: Exception):
        logger.error("Request failed (%s)", type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    for router in (health.router, auth.router, dashboard.router):
        application.include_router(router, prefix="/api/v1")
    return application


app = create_app()
