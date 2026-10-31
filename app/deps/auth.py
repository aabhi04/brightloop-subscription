from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.services.auth_service import decode_token
from app.utils.constants import Role
from app.utils.errors import Forbidden, Unauthorized

COOKIE_NAME = "access_token"


def _token_from_request(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(COOKIE_NAME)


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = _token_from_request(request)
    if not token:
        return None
    try:
        payload = decode_token(token)
    except Unauthorized:
        return None
    return db.get(User, int(payload["sub"]))


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise Unauthorized()
    return user


def require_roles(*roles: Role):
    """Dependency factory: allow only the given roles (API -> 403 JSON)."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise Forbidden()
        return user

    return checker


ADMIN_ONLY = require_roles(Role.ADMIN)
STAFF_OR_ADMIN = require_roles(Role.ADMIN, Role.STAFF)
CUSTOMER_ONLY = require_roles(Role.CUSTOMER)
