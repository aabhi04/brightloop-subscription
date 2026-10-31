from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps.auth import STAFF_OR_ADMIN
from app.models import Payment
from app.schemas.billing import PaymentIn, PaymentOut
from app.services import payment_service
from app.utils.constants import PaymentMethod
from app.utils.dates import today
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/payments", tags=["payments"], dependencies=[Depends(STAFF_OR_ADMIN)])


@router.post("", response_model=PaymentOut, status_code=201)
def create_payment(body: PaymentIn, db: Session = Depends(get_db)):
    return payment_service.record_payment(
        db,
        invoice_id=body.invoice_id,
        method=body.method,
        amount=body.amount,
        payment_date=body.payment_date or today(),
        note=body.note,
    )


@router.get("")
def list_payments(
    invoice_id: int | None = None,
    method: PaymentMethod | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    stmt = select(Payment).order_by(Payment.id.desc())
    if invoice_id:
        stmt = stmt.where(Payment.invoice_id == invoice_id)
    if method:
        stmt = stmt.where(Payment.method == method)
    if date_from:
        stmt = stmt.where(Payment.payment_date >= date_from)
    if date_to:
        stmt = stmt.where(Payment.payment_date <= date_to)
    page = paginate(db, stmt, params)
    page["items"] = [PaymentOut.model_validate(p) for p in page["items"]]
    return page
