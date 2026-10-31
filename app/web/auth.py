from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps.auth import COOKIE_NAME, get_optional_user
from app.models import User
from app.services import auth_service
from app.utils.errors import AppError
from app.web.common import HOME_BY_ROLE, PASSWORD_RULES, redirect, render

router = APIRouter()


def _login_response(user: User, next_url: str | None = None):
    # Only follow local paths, never an absolute URL from the query string.
    target = next_url if next_url and next_url.startswith("/") and not next_url.startswith("//") else HOME_BY_ROLE[user.role]
    response = redirect(target)
    response.set_cookie(
        COOKIE_NAME,
        auth_service.create_token(user),
        max_age=settings.jwt_expires_minutes * 60,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/")
def home(user: User | None = Depends(get_optional_user)):
    return redirect(HOME_BY_ROLE[user.role] if user else "/login")


@router.get("/login")
def login_page(request: Request, user: User | None = Depends(get_optional_user)):
    if user:
        return redirect(HOME_BY_ROLE[user.role])
    return render(request, "auth/login.html", next=request.query_params.get("next"), email="")


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(""),
    db: Session = Depends(get_db),
):
    try:
        user, _ = auth_service.login(db, email, password)
    except AppError as exc:
        return render(request, "auth/login.html", err=exc.message, email=email, next=next, status_code=400)
    return _login_response(user, next)


@router.post("/logout")
def logout():
    response = redirect("/login", msg="You have been logged out")
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/signup")
def signup_page(request: Request):
    return render(request, "auth/signup.html", password_rules=PASSWORD_RULES, name="", email="")


@router.post("/signup")
def signup_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        user = auth_service.signup(db, name, email, password)
    except AppError as exc:
        return render(
            request, "auth/signup.html", err=exc.message, password_rules=PASSWORD_RULES,
            name=name, email=email, status_code=400,
        )
    return _login_response(user)


@router.get("/forgot-password")
def forgot_page(request: Request):
    return render(request, "auth/forgot_password.html")


@router.post("/forgot-password")
def forgot_submit(email: str = Form(...), db: Session = Depends(get_db)):
    auth_service.forgot_password(db, email)
    return redirect("/login", msg="If that email is registered, a reset link has been sent.")


@router.get("/reset-password/{token}")
def reset_page(request: Request, token: str):
    return render(request, "auth/reset_password.html", token=token, password_rules=PASSWORD_RULES)


@router.post("/reset-password/{token}")
def reset_submit(request: Request, token: str, password: str = Form(...), db: Session = Depends(get_db)):
    try:
        auth_service.reset_password(db, token, password)
    except AppError as exc:
        return render(
            request, "auth/reset_password.html", token=token, password_rules=PASSWORD_RULES,
            err=exc.message, status_code=400,
        )
    return redirect("/login", msg="Password updated. You can now log in.")
