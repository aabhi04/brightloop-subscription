from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.deps.auth import get_optional_user
from app.models import User
from app.utils.constants import MAX_PAGE_SIZE, Role
from app.utils.errors import AppError
from app.utils.pagination import PageParams
from app.validators.password import RULES

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

PASSWORD_RULES = [(key, label) for key, label, _ in RULES]  # for the live checklist

HOME_BY_ROLE = {
    Role.ADMIN: "/admin",
    Role.STAFF: "/subscriptions",
    Role.CUSTOMER: "/portal/subscriptions",
}


class WebRedirect(Exception):
    """Raised by page guards; turned into a 303 redirect by the app."""

    def __init__(self, url: str):
        self.url = url


def web_user(*roles: Role):
    """Page guard: not logged in -> /login, wrong role -> that role's home page."""

    def guard(request: Request, user: User | None = Depends(get_optional_user)) -> User:
        if user is None:
            raise WebRedirect("/login?" + urlencode({"next": request.url.path}))
        if roles and user.role not in roles:
            raise WebRedirect(HOME_BY_ROLE[user.role] + "?" + urlencode({"err": "You do not have access to that page"}))
        return user

    return guard


ADMIN_PAGE = web_user(Role.ADMIN)
STAFF_PAGE = web_user(Role.ADMIN, Role.STAFF)
CUSTOMER_PAGE = web_user(Role.CUSTOMER)


def render(request: Request, template_name: str, user: User | None = None, status_code: int = 200, **context):
    context.update(
        user=user,
        msg=request.query_params.get("msg"),
        err=context.get("err") or request.query_params.get("err"),
    )
    return templates.TemplateResponse(request, template_name, context, status_code=status_code)


def redirect(url: str, msg: str | None = None, err: str | None = None) -> RedirectResponse:
    params = {k: v for k, v in (("msg", msg), ("err", err)) if v}
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params)
    return RedirectResponse(url, status_code=303)


def run_action(db, action, success_url: str, success_msg: str, error_url: str):
    """Run a form action; redirect with a success or error message (post/redirect/get)."""
    try:
        result = action()
    except AppError as exc:
        db.rollback()
        return redirect(error_url, err=exc.message)
    except IntegrityError:
        db.rollback()
        return redirect(error_url, err="This record is in use or duplicates an existing one")
    url = success_url(result) if callable(success_url) else success_url
    return redirect(url, msg=success_msg)


def parse(model, data: dict):
    """Validate form data with a Pydantic schema; turn errors into an AppError message."""
    try:
        return model(**data)
    except ValidationError as exc:
        parts = []
        for e in exc.errors():
            field = ".".join(str(p) for p in e["loc"])
            msg = str(e["msg"]).removeprefix("Value error, ")
            parts.append(f"{field}: {msg}" if field else msg)
        raise AppError("; ".join(parts))


def blank_to_none(value):
    return None if value is None or str(value).strip() == "" else value


def enum_or_none(enum_cls, value):
    try:
        return enum_cls(value) if value else None
    except ValueError:
        return None


def date_or_none(value) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def int_or_none(value) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


def page_args(request: Request, default_limit: int = 20):
    """page/limit from the query string, clamped like the API's."""
    page = max(1, int_or_none(request.query_params.get("page")) or 1)
    limit = min(MAX_PAGE_SIZE, max(1, int_or_none(request.query_params.get("limit")) or default_limit))
    return PageParams(page=page, limit=limit)


def lines_from_form(form) -> list[dict]:
    """Product rows posted as parallel lists: product_id / variant_id / quantity / tax_id."""
    products = form.getlist("product_id")
    variants = form.getlist("variant_id")
    quantities = form.getlist("quantity")
    taxes = form.getlist("tax_id")

    def at(values, i):
        return values[i] if i < len(values) else None

    return [
        {
            "product_id": int(product_id),
            "variant_id": int_or_none(at(variants, i)),
            "quantity": int_or_none(at(quantities, i)) or 1,
            "tax_id": int_or_none(at(taxes, i)),
        }
        for i, product_id in enumerate(products)
        if int_or_none(product_id)
    ]


def form_bool(form, name: str) -> bool:
    return form.get(name) in ("on", "true", "1", "yes")


def url_with(request: Request, **params) -> str:
    """Current URL with some query parameters replaced (used by pagination and filters)."""
    query = dict(request.query_params)
    query.pop("msg", None)
    query.pop("err", None)
    for key, value in params.items():
        if value is None:
            query.pop(key, None)
        else:
            query[key] = value
    return request.url.path + ("?" + urlencode(query) if query else "")


def fmt_money(value) -> str:
    if value is None or value == "":
        return "-"
    try:
        return f"{Decimal(value):,.2f}"
    except (InvalidOperation, ValueError):
        return str(value)


def fmt_date(value) -> str:
    if not value:
        return "-"
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    return str(value)


templates.env.globals["url_with"] = url_with
templates.env.filters["money"] = fmt_money
templates.env.filters["date"] = fmt_date
