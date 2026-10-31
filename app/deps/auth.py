from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.services.auth_service import decode_token
from app.utils.constants import Role
from app.utils.errors import Forbidden, Unauthorized

COOKIE_NAME = "access_token"


# auto_error=False: the cookie is an alternative; this also adds "Authorize" to /docs.
bearer_scheme = HTTPBearer(auto_error=False)


def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    token = credentials.credentials if credentials else request.cookies.get(COOKIE_NAME)
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
