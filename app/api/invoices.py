from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps.auth import STAFF_OR_ADMIN
from app.schemas.billing import GenerateDueIn, InvoiceOut, InvoiceSummaryOut
from app.services import billing_service, invoice_service
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/invoices", tags=["invoices"], dependencies=[Depends(STAFF_OR_ADMIN)])


@router.get("")
def list_invoices(
    stmt=Depends(invoice_service.invoice_list_query),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    page = paginate(db, stmt, params)
    page["items"] = [InvoiceSummaryOut.model_validate(i) for i in page["items"]]
    return page


@router.post("/generate-due")
def generate_due(body: GenerateDueIn | None = Body(default=None), db: Session = Depends(get_db)):
    """Same service the daily scheduler calls. `on_date` (optional) bills as of that date."""
    return billing_service.generate_due_invoices(db, body.on_date if body else None)


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return invoice_service.get_invoice(db, invoice_id)


@router.patch("/{invoice_id}/confirm", response_model=InvoiceOut)
def confirm_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return invoice_service.confirm_invoice(db, invoice_id)


@router.patch("/{invoice_id}/cancel", response_model=InvoiceOut)
def cancel_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return invoice_service.cancel_invoice(db, invoice_id)


@router.patch("/{invoice_id}/send", response_model=InvoiceOut)
def send_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return invoice_service.send_invoice(db, invoice_id)
