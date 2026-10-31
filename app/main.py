import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import api_router
from app.config import settings
from app.db import engine
from app.jobs.scheduler import start_scheduler
from app.utils.errors import AppError

logger = logging.getLogger("brightloop")


def _validation_message(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err.get("loc", []) if p not in ("body", "query", "path"))
        msg = str(err.get("msg", "Invalid input")).removeprefix("Value error, ")
        parts.append(f"{field}: {msg}" if field else msg)
    return "; ".join(parts) or "Invalid input"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return JSONResponse({"error": exc.message}, status_code=exc.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse({"error": _validation_message(exc)}, status_code=422)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        return JSONResponse(
            {"error": "This change conflicts with existing data (duplicate value or record still in use)"},
            status_code=409,
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"error": "Internal server error"}, status_code=500)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = start_scheduler() if settings.enable_scheduler else None
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(title="Brightloop Subscription Management", lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(api_router)

    @app.get("/api/health")
    def health():
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


app = create_app()
