import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import api_router
from app.config import settings
from app.db import SessionLocal, engine
from app.deps.auth import COOKIE_NAME
from app.jobs.scheduler import start_scheduler
from app.models import User
from app.services.auth_service import decode_token
from app.utils.errors import AppError
from app.web import web_router
from app.web.common import WebRedirect, render

logger = logging.getLogger("brightloop")
STATIC_DIR = Path(__file__).resolve().parent / "static"


def _validation_message(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err.get("loc", []) if p not in ("body", "query", "path"))
        msg = str(err.get("msg", "Invalid input")).removeprefix("Value error, ")
        parts.append(f"{field}: {msg}" if field else msg)
    return "; ".join(parts) or "Invalid input"


def _is_api(request: Request) -> bool:
    return request.url.path.startswith("/api")


def _cookie_user(request: Request) -> User | None:
    """Best-effort lookup so HTML error pages keep the sidebar for logged-in users."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        user_id = int(decode_token(token)["sub"])
    except Exception:
        return None
    with SessionLocal() as db:
        return db.get(User, user_id)


def error_response(request: Request, message: str, status_code: int):
    if _is_api(request):
        return JSONResponse({"error": message}, status_code=status_code)
    return render(
        request, "error.html", _cookie_user(request), status_code=status_code,
        message=message, status_code_value=status_code,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(WebRedirect)
    async def web_redirect(request: Request, exc: WebRedirect):
        return RedirectResponse(exc.url, status_code=303)

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return error_response(request, exc.message, exc.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return error_response(request, str(exc.detail), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error_response(request, _validation_message(exc), 422)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        return error_response(
            request, "This change conflicts with existing data (duplicate value or record still in use)", 409
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(request, "Internal server error", 500)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = start_scheduler() if settings.enable_scheduler else None
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(title="Brightloop Subscription Management", lifespan=lifespan)
    register_error_handlers(app)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(api_router)
    app.include_router(web_router)

    @app.get("/api/health")
    def health():
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


app = create_app()
