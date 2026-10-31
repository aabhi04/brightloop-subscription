from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Payment
from app.services.invoice_service import get_invoice
from app.utils.constants import InvoiceStatus, PaymentMethod
from app.utils.errors import AppError
from app.utils.money import money


def record_payment(
    db: Session,
    *,
    invoice_id: int,
    method: PaymentMethod,
    amount: Decimal,
    payment_date: date,
    note: str | None = None,
) -> Payment:
    """Record a full or partial payment; marks the invoice PAID once fully covered."""
    amount = money(amount)
    if amount <= 0:
        raise AppError("Payment amount must be greater than zero")

    invoice = get_invoice(db, invoice_id, lock=True)  # serialises concurrent payments
    if invoice.status == InvoiceStatus.DRAFT:
        raise AppError("Confirm the invoice before recording payments")
    if invoice.status == InvoiceStatus.PAID:
        raise AppError("Invoice is already fully paid")
    if invoice.status == InvoiceStatus.CANCELLED:
        raise AppError("Cannot pay a cancelled invoice")
    if amount > invoice.balance:
        raise AppError(f"Payment of {amount} exceeds the outstanding balance of {invoice.balance}")

    payment = Payment(invoice_id=invoice.id, method=method, amount=amount, payment_date=payment_date, note=note)
    db.add(payment)
    invoice.amount_paid = money(invoice.amount_paid + amount)
    if invoice.amount_paid >= invoice.total:
        invoice.status = InvoiceStatus.PAID
    db.commit()
    return payment
