from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas import ORMModel
from app.utils.constants import Role


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    password: str


class UserCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str


class UserOut(ORMModel):
    id: int
    name: str
    email: str
    role: Role
    created_at: datetime


class TokenOut(BaseModel):
    token: str
    user: UserOut
