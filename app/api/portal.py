from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps.auth import CUSTOMER_ONLY
from app.models import Invoice, User
from app.schemas.billing import InvoiceOut, InvoiceSummaryOut
from app.schemas.subscription import SubscriptionOut, SubscriptionSummaryOut
from app.services import invoice_service, subscription_service
from app.utils.constants import InvoiceStatus, SubscriptionStatus
from app.utils.errors import NotFound
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/portal", tags=["portal"])


# customer_id always comes from the token, never from the query string.
@router.get("/subscriptions")
def my_subscriptions(
    status: SubscriptionStatus | None = None,
    params: PageParams = Depends(page_params),
    user: User = Depends(CUSTOMER_ONLY),
    db: Session = Depends(get_db),
):
    stmt = subscription_service.subscription_list_query(status=status, customer_id=user.id)
    page = paginate(db, stmt, params)
    page["items"] = [SubscriptionSummaryOut.model_validate(s) for s in page["items"]]
    return page


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionOut)
def my_subscription(subscription_id: int, user: User = Depends(CUSTOMER_ONLY), db: Session = Depends(get_db)):
    sub = subscription_service.get_subscription(db, subscription_id)
    if sub.customer_id != user.id:
        raise NotFound("Subscription")
    return sub


@router.get("/invoices")
def my_invoices(
    status: InvoiceStatus | None = None,
    params: PageParams = Depends(page_params),
    user: User = Depends(CUSTOMER_ONLY),
    db: Session = Depends(get_db),
):
    stmt = invoice_service.invoice_list_query(status=status, customer_id=user.id)
    # Draft invoices are internal until staff confirm them.
    stmt = stmt.where(Invoice.status != InvoiceStatus.DRAFT)
    page = paginate(db, stmt, params)
    page["items"] = [InvoiceSummaryOut.model_validate(i) for i in page["items"]]
    return page


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def my_invoice(invoice_id: int, user: User = Depends(CUSTOMER_ONLY), db: Session = Depends(get_db)):
    invoice = invoice_service.get_invoice_for_customer(db, invoice_id, user)
    if invoice.status == InvoiceStatus.DRAFT:
        raise NotFound("Invoice")
    return invoice
