from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps.auth import ADMIN_ONLY, STAFF_OR_ADMIN, get_current_user
from app.models import User
from app.schemas.auth import UserCreateIn, UserOut
from app.services import auth_service
from app.utils.constants import Role
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/staff", response_model=UserOut, status_code=201, dependencies=[Depends(ADMIN_ONLY)])
def create_staff(body: UserCreateIn, db: Session = Depends(get_db)):
    user = auth_service.create_user(db, body.name, body.email, body.password, Role.STAFF)
    db.commit()
    return user


@router.post("/customers", response_model=UserOut, status_code=201, dependencies=[Depends(STAFF_OR_ADMIN)])
def create_customer(body: UserCreateIn, db: Session = Depends(get_db)):
    user = auth_service.create_user(db, body.name, body.email, body.password, Role.CUSTOMER)
    db.commit()
    return user


@router.get("", dependencies=[Depends(STAFF_OR_ADMIN)])
def list_users(
    role: Role | None = None,
    q: str | None = Query(None, description="Search name or email"),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    stmt = select(User).order_by(User.id)
    # Staff only see customers; admins see everyone.
    if current.role == Role.STAFF:
        stmt = stmt.where(User.role == Role.CUSTOMER)
    if role:
        stmt = stmt.where(User.role == role)
    if q:
        stmt = stmt.where(or_(User.name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    page = paginate(db, stmt, params)
    page["items"] = [UserOut.model_validate(u) for u in page["items"]]
    return page
