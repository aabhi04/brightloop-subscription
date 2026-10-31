from datetime import date

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.deps.auth import STAFF_OR_ADMIN
from app.models import Subscription
from app.schemas.subscription import (
    FromTemplateIn,
    StatusIn,
    SubscriptionIn,
    SubscriptionOut,
    SubscriptionSummaryOut,
)
from app.services import subscription_service
from app.utils.constants import SubscriptionStatus
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"], dependencies=[Depends(STAFF_OR_ADMIN)])


def subscription_list_query(
    status: SubscriptionStatus | None = None,
    customer_id: int | None = None,
    plan_id: int | None = None,
    q: str | None = None,
    start_from: date | None = None,
    start_to: date | None = None,
):
    stmt = (
        select(Subscription)
        .options(joinedload(Subscription.customer), joinedload(Subscription.plan))
        .order_by(Subscription.id.desc())
    )
    if status:
        stmt = stmt.where(Subscription.status == status)
    if customer_id:
        stmt = stmt.where(Subscription.customer_id == customer_id)
    if plan_id:
        stmt = stmt.where(Subscription.plan_id == plan_id)
    if q:
        stmt = stmt.where(Subscription.number.ilike(f"%{q}%"))
    if start_from:
        stmt = stmt.where(Subscription.start_date >= start_from)
    if start_to:
        stmt = stmt.where(Subscription.start_date <= start_to)
    return stmt


@router.get("")
def list_subscriptions(
    stmt=Depends(subscription_list_query),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    page = paginate(db, stmt, params)
    page["items"] = [SubscriptionSummaryOut.model_validate(s) for s in page["items"]]
    return page


@router.get("/{subscription_id}", response_model=SubscriptionOut)
def get_subscription(subscription_id: int, db: Session = Depends(get_db)):
    return subscription_service.get_subscription(db, subscription_id)


@router.post("", response_model=SubscriptionOut, status_code=201)
def create_subscription(body: SubscriptionIn, db: Session = Depends(get_db)):
    data = body.model_dump()
    return subscription_service.create_subscription(db, **data)


@router.post("/from-template/{template_id}", response_model=SubscriptionOut, status_code=201)
def create_from_template(template_id: int, body: FromTemplateIn, db: Session = Depends(get_db)):
    return subscription_service.create_from_template(
        db, template_id, body.customer_id, body.start_date, body.payment_terms
    )


@router.put("/{subscription_id}", response_model=SubscriptionOut)
def update_subscription(subscription_id: int, body: SubscriptionIn, db: Session = Depends(get_db)):
    return subscription_service.update_subscription(db, subscription_id, **body.model_dump())


@router.delete("/{subscription_id}", status_code=204)
def delete_subscription(subscription_id: int, db: Session = Depends(get_db)):
    subscription_service.delete_subscription(db, subscription_id)
    return Response(status_code=204)


@router.patch("/{subscription_id}/status", response_model=SubscriptionOut)
def change_status(subscription_id: int, body: StatusIn, db: Session = Depends(get_db)):
    return subscription_service.change_status(db, subscription_id, body.status)
