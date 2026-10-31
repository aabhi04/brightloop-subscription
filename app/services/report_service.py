from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Invoice, Payment, Subscription
from app.services.invoice_service import overdue_condition
from app.utils.constants import InvoiceStatus, PaymentMethod, SubscriptionStatus
from app.utils.dates import today
from app.utils.money import ZERO, money
from app.utils.pagination import PageParams, paginate


def summary(
    db: Session,
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: int | None = None,
) -> dict:
    """Headline numbers, each a single aggregate query.

    - revenue_received: payments whose payment_date is in the range
    - outstanding / overdue: open (CONFIRMED) invoices whose billing period starts in the range
    """
    active = select(func.count(Subscription.id)).where(Subscription.status == SubscriptionStatus.ACTIVE)
    if customer_id:
        active = active.where(Subscription.customer_id == customer_id)

    revenue = select(func.coalesce(func.sum(Payment.amount), 0))
    if date_from:
        revenue = revenue.where(Payment.payment_date >= date_from)
    if date_to:
        revenue = revenue.where(Payment.payment_date <= date_to)
    if customer_id:
        revenue = revenue.join(Invoice, Invoice.id == Payment.invoice_id).where(Invoice.customer_id == customer_id)

    def open_invoices(stmt):
        stmt = stmt.where(Invoice.status == InvoiceStatus.CONFIRMED)
        if date_from:
            stmt = stmt.where(Invoice.billing_period_start >= date_from)
        if date_to:
            stmt = stmt.where(Invoice.billing_period_start <= date_to)
        if customer_id:
            stmt = stmt.where(Invoice.customer_id == customer_id)
        return stmt

    balance = func.coalesce(func.sum(Invoice.total - Invoice.amount_paid), 0)
    outstanding = db.execute(open_invoices(select(balance, func.count(Invoice.id)))).one()
    overdue = db.execute(open_invoices(select(balance, func.count(Invoice.id)).where(overdue_condition()))).one()

    return {
        "active_subscriptions": db.scalar(active),
        "revenue_received": money(db.scalar(revenue) or ZERO),
        "outstanding_amount": money(outstanding[0]),
        "open_invoices": outstanding[1],
        "overdue_amount": money(overdue[0]),
        "overdue_invoices": overdue[1],
    }


def revenue_by_month(
    db: Session,
    params: PageParams,
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: int | None = None,
    method: PaymentMethod | None = None,
) -> dict:
    month = func.date_trunc("month", Payment.payment_date).label("month")
    stmt = select(
        month,
        func.sum(Payment.amount).label("amount"),
        func.count(Payment.id).label("payments"),
    )
    if customer_id:
        stmt = stmt.join(Invoice, Invoice.id == Payment.invoice_id).where(Invoice.customer_id == customer_id)
    if date_from:
        stmt = stmt.where(Payment.payment_date >= date_from)
    if date_to:
        stmt = stmt.where(Payment.payment_date <= date_to)
    if method:
        stmt = stmt.where(Payment.method == method)
    stmt = stmt.group_by(month).order_by(month.desc())

    page = paginate(db, stmt, params, scalars=False)
    page["items"] = [
        {"month": row.month.date().isoformat()[:7], "amount": row.amount, "payments": row.payments}
        for row in page["items"]
    ]
    return page


def overdue_invoices_query(
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: int | None = None,
):
    """Overdue invoices, oldest due first. date_from/date_to filter on due_date."""
    stmt = (
        select(Invoice)
        .options(joinedload(Invoice.customer))
        .where(overdue_condition())
        .order_by(Invoice.due_date, Invoice.id)
    )
    if date_from:
        stmt = stmt.where(Invoice.due_date >= date_from)
    if date_to:
        stmt = stmt.where(Invoice.due_date <= date_to)
    if customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    return stmt


def days_overdue(invoice: Invoice) -> int:
    return (today() - invoice.due_date).days
