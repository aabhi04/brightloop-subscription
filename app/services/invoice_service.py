from datetime import date, datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Invoice, User
from app.services.email_service import send_email
from app.utils.constants import InvoiceStatus
from app.utils.dates import today
from app.utils.errors import AppError, NotFound


def overdue_condition(on_date: date | None = None):
    """SQL condition for rule 11: CONFIRMED, not fully paid, due date passed."""
    on_date = on_date or today()
    return and_(
        Invoice.status == InvoiceStatus.CONFIRMED,
        Invoice.amount_paid < Invoice.total,
        Invoice.due_date < on_date,
    )


def is_overdue(invoice: Invoice, on_date: date | None = None) -> bool:
    on_date = on_date or today()
    return (
        invoice.status == InvoiceStatus.CONFIRMED
        and invoice.amount_paid < invoice.total
        and invoice.due_date < on_date
    )


def invoice_list_query(
    status: InvoiceStatus | None = None,
    customer_id: int | None = None,
    subscription_id: int | None = None,
    overdue: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = None,
):
    """Shared filters for staff lists, the customer portal and reports.

    date_from/date_to filter on billing_period_start.
    """
    stmt = select(Invoice).options(joinedload(Invoice.customer)).order_by(Invoice.id.desc())
    if status:
        stmt = stmt.where(Invoice.status == status)
    if customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    if subscription_id:
        stmt = stmt.where(Invoice.subscription_id == subscription_id)
    if overdue:
        stmt = stmt.where(overdue_condition())
    if date_from:
        stmt = stmt.where(Invoice.billing_period_start >= date_from)
    if date_to:
        stmt = stmt.where(Invoice.billing_period_start <= date_to)
    if q:
        stmt = stmt.where(Invoice.number.ilike(f"%{q}%"))
    return stmt


def get_invoice(db: Session, invoice_id: int, lock: bool = False) -> Invoice:
    stmt = select(Invoice).where(Invoice.id == invoice_id)
    if lock:
        stmt = stmt.with_for_update()
    invoice = db.scalars(stmt).one_or_none()
    if not invoice:
        raise NotFound("Invoice")
    return invoice


def get_invoice_for_customer(db: Session, invoice_id: int, customer: User) -> Invoice:
    invoice = get_invoice(db, invoice_id)
    # Same 404 as a missing invoice, so customers cannot probe other customers' ids.
    if invoice.customer_id != customer.id:
        raise NotFound("Invoice")
    return invoice


def confirm_invoice(db: Session, invoice_id: int) -> Invoice:
    invoice = get_invoice(db, invoice_id, lock=True)
    if invoice.status != InvoiceStatus.DRAFT:
        raise AppError(f"Only DRAFT invoices can be confirmed (current status: {invoice.status.value})")
    # A fully discounted invoice has nothing to collect.
    invoice.status = InvoiceStatus.PAID if invoice.total <= 0 else InvoiceStatus.CONFIRMED
    db.commit()
    return invoice


def cancel_invoice(db: Session, invoice_id: int) -> Invoice:
    invoice = get_invoice(db, invoice_id, lock=True)
    if invoice.status not in (InvoiceStatus.DRAFT, InvoiceStatus.CONFIRMED):
        raise AppError(f"Only DRAFT or CONFIRMED invoices can be cancelled (current status: {invoice.status.value})")
    if invoice.amount_paid > 0:
        raise AppError("Invoice has payments recorded and cannot be cancelled")
    invoice.status = InvoiceStatus.CANCELLED
    db.commit()
    return invoice


def send_invoice(db: Session, invoice_id: int) -> Invoice:
    invoice = get_invoice(db, invoice_id)
    if invoice.status not in (InvoiceStatus.CONFIRMED, InvoiceStatus.PAID):
        raise AppError("Confirm the invoice before sending it")
    customer = invoice.customer
    lines = "\n".join(f"  - {l.description}: {l.quantity} x {l.unit_price} = {l.amount}" for l in invoice.lines)
    send_email(
        customer.email,
        f"Invoice {invoice.number} from Brightloop",
        f"Hi {customer.name},\n\nInvoice {invoice.number} for "
        f"{invoice.billing_period_start} to {invoice.billing_period_end}:\n{lines}\n\n"
        f"Subtotal: {invoice.subtotal}\nDiscount: -{invoice.discount_total}\nTax: {invoice.tax_total}\n"
        f"Total: {invoice.total}\nPaid: {invoice.amount_paid}\nBalance due: {invoice.balance}\n"
        f"Due date: {invoice.due_date}\n",
    )
    invoice.sent_at = datetime.now(timezone.utc)
    db.commit()
    return invoice
