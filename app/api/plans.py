from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps.auth import ADMIN_ONLY, STAFF_OR_ADMIN
from app.models import Plan
from app.schemas.catalog import PlanIn, PlanOut
from app.services import plan_service
from app.utils.constants import BillingPeriod, PlanStatus
from app.utils.errors import get_or_404
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("", dependencies=[Depends(STAFF_OR_ADMIN)])
def list_plans(
    status: PlanStatus | None = None,
    billing_period: BillingPeriod | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    stmt = select(Plan).order_by(Plan.id)
    if status:
        stmt = stmt.where(Plan.status == status)
    if billing_period:
        stmt = stmt.where(Plan.billing_period == billing_period)
    page = paginate(db, stmt, params)
    page["items"] = [PlanOut.model_validate(p) for p in page["items"]]
    return page


@router.get("/{plan_id}", response_model=PlanOut, dependencies=[Depends(STAFF_OR_ADMIN)])
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, Plan, plan_id)


@router.post("", response_model=PlanOut, status_code=201, dependencies=[Depends(ADMIN_ONLY)])
def create_plan(body: PlanIn, db: Session = Depends(get_db)):
    plan = Plan(**body.model_dump())
    db.add(plan)
    db.commit()
    return plan


@router.put("/{plan_id}", response_model=PlanOut, dependencies=[Depends(ADMIN_ONLY)])
def update_plan(plan_id: int, body: PlanIn, db: Session = Depends(get_db)):
    plan = get_or_404(db, Plan, plan_id)
    for key, value in body.model_dump().items():
        setattr(plan, key, value)
    db.commit()
    return plan


@router.delete("/{plan_id}", status_code=204, dependencies=[Depends(ADMIN_ONLY)])
def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Plan, plan_id))
    db.commit()
    return Response(status_code=204)


@router.patch("/{plan_id}/close", response_model=PlanOut, dependencies=[Depends(ADMIN_ONLY)])
def close_plan(plan_id: int, db: Session = Depends(get_db)):
    return plan_service.close_plan(db, plan_id)


@router.patch("/{plan_id}/pause", response_model=PlanOut, dependencies=[Depends(ADMIN_ONLY)])
def pause_plan(plan_id: int, db: Session = Depends(get_db)):
    return plan_service.pause_plan(db, plan_id)


@router.patch("/{plan_id}/renew", response_model=PlanOut, dependencies=[Depends(ADMIN_ONLY)])
def renew_plan(plan_id: int, db: Session = Depends(get_db)):
    return plan_service.renew_plan(db, plan_id)
