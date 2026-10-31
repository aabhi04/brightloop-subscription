from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.auth import ForgotPasswordIn, LoginIn, ResetPasswordIn, SignupIn, TokenOut, UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenOut, status_code=201)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    user = auth_service.signup(db, body.name, body.email, body.password)
    return {"token": auth_service.create_token(user), "user": user}


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user, token = auth_service.login(db, body.email, body.password)
    return {"token": token, "user": UserOut.model_validate(user)}


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordIn, db: Session = Depends(get_db)):
    auth_service.forgot_password(db, body.email)
    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password/{token}")
def reset_password(token: str, body: ResetPasswordIn, db: Session = Depends(get_db)):
    auth_service.reset_password(db, token, body.password)
    return {"message": "Password updated. You can now log in."}
