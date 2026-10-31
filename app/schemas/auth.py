import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.schemas import ORMModel
from app.utils.constants import Role

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _check_email(value: str) -> str:
    # A shape check only, so internal domains such as brightloop.local are accepted.
    value = value.strip().lower()
    if len(value) > 255 or not EMAIL_PATTERN.match(value):
        raise ValueError("Enter a valid email address")
    return value


EmailStr = Annotated[str, AfterValidator(_check_email)]


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
