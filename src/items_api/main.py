from __future__ import annotations

import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from items_api.api.responses import error_response, http_status_to_code, request_id_of
from items_api.config import get_settings
from items_api.db import close_db, connect_db, get_database
from items_api.middleware.envelope import ResponseEnvelopeMiddleware
from items_api.middleware.idempotency import IdempotencyMiddleware
from items_api.middleware.rate_limit import RateLimitMiddleware
from items_api.middleware.request_id import RequestIdMiddleware
from items_api.middleware.security import CsrfMiddleware, SecurityHeadersMiddleware
from items_api.repositories.item_repository import ItemRepository
from items_api.repositories.user_repository import UserRepository
from items_api.routes.auth import router as auth_router
from items_api.routes.health import router as health_router
from items_api.routes.items import router as items_router
from items_api.routes.users import router as users_router
from items_api.stores import create_store
from items_api.stores.redis_store import RedisStore

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            '{"time":"%(asctime)s","level":"%(levelname)s",'
            '"logger":"%(name)s","message":"%(message)s"}'
        ),
        datefmt="%Y-%m-%dT%H:%M:%S",
        force=True,
    )


configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    from items_api.security.audit import validate_runtime_settings

    settings = get_settings()
    validate_runtime_settings(settings)
    logger.info(
        "Starting %s v%s environment=%s use_redis=%s",
        settings.app_name,
        settings.app_version,
        settings.environment,
        settings.use_redis,
    )
    await connect_db()
    store = create_store(settings)
    database = get_database()
    item_repo = ItemRepository(database["items"])
    user_repo = UserRepository(database["users"])
    app.state.store = store
    app.state.settings = settings

    async def _ensure_indexes() -> None:
        try:
            await item_repo.ensure_indexes()
            await user_repo.ensure_indexes()
            logger.info("Mongo indexes ready")
        except Exception:
            logger.exception("Failed to ensure Mongo indexes")

    index_task = asyncio.create_task(_ensure_indexes())
    try:
        yield
    finally:
        if not index_task.done():
            index_task.cancel()
            try:
                await index_task
            except asyncio.CancelledError:
                pass
        if isinstance(store, RedisStore):
            await store.aclose()
        await close_db()
        logger.info("%s shut down", settings.app_name)


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.add_middleware(ResponseEnvelopeMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CsrfMiddleware)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=settings.cors_methods_list,
    allow_headers=settings.cors_headers_list,
    expose_headers=settings.cors_expose_list,
    max_age=settings.cors_max_age_seconds,
)

app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(users_router, prefix=settings.api_prefix)
app.include_router(items_router, prefix=settings.api_prefix)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("detail") or "Request failed")
        code = str(detail.get("code") or http_status_to_code(exc.status_code))
        details = detail.get("details")
    else:
        message = str(detail)
        code = http_status_to_code(exc.status_code)
        details = None
    return error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        details=details,
        request_id=request_id_of(request),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Validation failed",
        details=exc.errors(),
        request_id=request_id_of(request),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = request_id_of(request)
    logger.error(
        "Unhandled exception request_id=%s: %s\n%s",
        request_id,
        exc,
        traceback.format_exc(),
    )
    return error_response(
        status_code=500,
        code="INTERNAL_ERROR",
        message="Internal server error",
        request_id=request_id,
    )


@app.get("/")
async def root():
    return {
        "message": settings.app_name,
        "version": settings.app_version,
        "api_prefix": settings.api_prefix,
        "docs": None if settings.is_production else "/docs",
    }
