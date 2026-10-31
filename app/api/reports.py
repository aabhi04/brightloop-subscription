from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps.auth import STAFF_OR_ADMIN
from app.schemas.billing import OverdueInvoiceOut, ReportSummaryOut, RevenueRowOut
from app.schemas.subscription import SubscriptionSummaryOut
from app.services import report_service, subscription_service
from app.utils.constants import PaymentMethod, SubscriptionStatus
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(STAFF_OR_ADMIN)])


@router.get("/summary", response_model=ReportSummaryOut)
def summary(
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: int | None = None,
    db: Session = Depends(get_db),
):
    return report_service.summary(db, date_from, date_to, customer_id)


@router.get("/active-subscriptions")
def active_subscriptions(
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    customer_id: int | None = None,
    plan_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    stmt = subscription_service.subscription_list_query(
        status=status, customer_id=customer_id, plan_id=plan_id, start_from=date_from, start_to=date_to
    )
    page = paginate(db, stmt, params)
    page["items"] = [SubscriptionSummaryOut.model_validate(s) for s in page["items"]]
    return page


@router.get("/revenue")
def revenue(
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: int | None = None,
    method: PaymentMethod | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    page = report_service.revenue_by_month(db, params, date_from, date_to, customer_id, method)
    page["items"] = [RevenueRowOut(**row) for row in page["items"]]
    return page


@router.get("/overdue")
def overdue(
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: int | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    page = paginate(db, report_service.overdue_invoices_query(date_from, date_to, customer_id), params)
    page["items"] = [
        OverdueInvoiceOut.model_validate(i).model_copy(update={"days_overdue": report_service.days_overdue(i)})
        for i in page["items"]
    ]
    return page
