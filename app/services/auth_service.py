import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User
from app.services.email_service import send_email
from app.utils.constants import Role
from app.utils.errors import AppError, Unauthorized
from app.validators.password import password_errors

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise Unauthorized("Invalid or expired token")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_user(db: Session, name: str, email: str, password: str, role: Role) -> User:
    """Validate and insert a user. Caller commits."""
    errors = password_errors(password)
    if errors:
        raise AppError("Password does not meet requirements: " + "; ".join(errors))
    email = normalize_email(email)
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise AppError("Email is already registered", 409)
    if not name.strip():
        raise AppError("Name is required")
    user = User(name=name.strip(), email=email, password_hash=hash_password(password), role=role)
    db.add(user)
    db.flush()
    return user


def signup(db: Session, name: str, email: str, password: str) -> User:
    # Public signup always creates a CUSTOMER, whatever the client sends.
    user = create_user(db, name, email, password, Role.CUSTOMER)
    db.commit()
    return user


def login(db: Session, email: str, password: str) -> tuple[User, str]:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if not user or not verify_password(password, user.password_hash):
        raise Unauthorized("Invalid email or password")
    return user, create_token(user)


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def forgot_password(db: Session, email: str) -> None:
    """Create a reset token and email the link. Silent if the email is unknown."""
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if not user:
        return
    token = secrets.token_urlsafe(32)
    # Only a hash is stored, so a leaked database cannot be used to reset passwords.
    user.reset_token = _hash_reset_token(token)
    user.reset_token_expiry = datetime.now(timezone.utc) + timedelta(minutes=settings.reset_token_expires_minutes)
    db.commit()
    link = f"{settings.app_url}/reset-password/{token}"
    send_email(
        user.email,
        "Reset your Brightloop password",
        f"Hi {user.name},\n\nReset your password using this link (valid for "
        f"{settings.reset_token_expires_minutes} minutes):\n{link}\n\nIf you did not ask for this, ignore this email.",
    )


def reset_password(db: Session, token: str, new_password: str) -> None:
    user = db.scalar(select(User).where(User.reset_token == _hash_reset_token(token)))
    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.now(timezone.utc):
        raise AppError("Reset link is invalid or has expired")
    errors = password_errors(new_password)
    if errors:
        raise AppError("Password does not meet requirements: " + "; ".join(errors))
    user.password_hash = hash_password(new_password)
    user.reset_token = None
    user.reset_token_expiry = None
    db.commit()
