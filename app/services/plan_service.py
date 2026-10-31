from datetime import date

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Plan
from app.utils.constants import PlanStatus
from app.utils.dates import add_period, today
from app.utils.errors import AppError, NotFound


def get_plan(db: Session, plan_id: int) -> Plan:
    plan = db.get(Plan, plan_id)
    if not plan:
        raise NotFound("Plan")
    return plan


def close_plan(db: Session, plan_id: int) -> Plan:
    plan = get_plan(db, plan_id)
    if not plan.closable:
        raise AppError("This plan does not allow closing")
    if plan.status == PlanStatus.CLOSED:
        raise AppError("Plan is already closed")
    plan.status = PlanStatus.CLOSED
    db.commit()
    return plan


def pause_plan(db: Session, plan_id: int) -> Plan:
    plan = get_plan(db, plan_id)
    if not plan.pausable:
        raise AppError("This plan does not allow pausing")
    if plan.status != PlanStatus.ACTIVE:
        raise AppError(f"Only an ACTIVE plan can be paused (current status: {plan.status.value})")
    plan.status = PlanStatus.PAUSED
    db.commit()
    return plan


def renew_plan(db: Session, plan_id: int) -> Plan:
    """Reactivate the plan and extend its end date by one billing period."""
    plan = get_plan(db, plan_id)
    if not plan.renewable:
        raise AppError("This plan does not allow renewing")
    if plan.end_date:
        plan.end_date = add_period(max(plan.end_date, today()), plan.billing_period)
    plan.status = PlanStatus.ACTIVE
    db.commit()
    return plan


def auto_close_expired_plans(db: Session, on_date: date | None = None) -> int:
    """Close plans with auto_close=True whose end_date has passed. Returns how many."""
    on_date = on_date or today()
    result = db.execute(
        update(Plan)
        .where(Plan.auto_close.is_(True), Plan.end_date.is_not(None), Plan.end_date < on_date)
        .where(Plan.status != PlanStatus.CLOSED)
        .values(status=PlanStatus.CLOSED)
    )
    db.commit()
    return result.rowcount
