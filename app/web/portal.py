from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Invoice, Subscription, User
from app.services import invoice_service, subscription_service
from app.utils.constants import InvoiceStatus, SubscriptionStatus
from app.utils.errors import NotFound
from app.utils.pagination import paginate
from app.web.common import CUSTOMER_PAGE, enum_or_none, page_args, render

router = APIRouter(prefix="/portal")

# Every query here is scoped to the logged-in customer's id.


@router.get("/subscriptions")
def my_subscriptions(request: Request, user: User = Depends(CUSTOMER_PAGE), db: Session = Depends(get_db)):
    status = enum_or_none(SubscriptionStatus, request.query_params.get("status"))
    stmt = subscription_service.subscription_list_query(status=status, customer_id=user.id).options(
        selectinload(Subscription.lines)
    )
    page = paginate(db, stmt, page_args(request))
    statuses = [(s.value, s.value.title()) for s in SubscriptionStatus]
    return render(request, "portal/subscriptions.html", user, page=page, statuses=statuses, filters=request.query_params)


@router.get("/invoices")
def my_invoices(request: Request, user: User = Depends(CUSTOMER_PAGE), db: Session = Depends(get_db)):
    status = enum_or_none(InvoiceStatus, request.query_params.get("status"))
    stmt = invoice_service.invoice_list_query(status=status, customer_id=user.id).where(
        Invoice.status != InvoiceStatus.DRAFT
    )
    page = paginate(db, stmt, page_args(request))
    statuses = [(s.value, s.value.title()) for s in InvoiceStatus if s != InvoiceStatus.DRAFT]
    return render(
        request, "portal/invoices.html", user, page=page, statuses=statuses, filters=request.query_params,
        is_overdue=invoice_service.is_overdue,
    )


@router.get("/invoices/{invoice_id}")
def my_invoice(invoice_id: int, request: Request, user: User = Depends(CUSTOMER_PAGE), db: Session = Depends(get_db)):
    invoice = invoice_service.get_invoice_for_customer(db, invoice_id, user)
    if invoice.status == InvoiceStatus.DRAFT:
        raise NotFound("Invoice")
    return render(
        request, "staff/invoice_detail.html", user, invoice=invoice,
        overdue=invoice_service.is_overdue(invoice), staff_view=False,
    )
