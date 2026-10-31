import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceLine, Plan, Subscription
from app.services.discount_service import DraftLine, apply_discounts
from app.services.tax_service import line_tax
from app.utils.constants import InvoiceStatus, PlanStatus, SubscriptionStatus
from app.utils.dates import add_period, period_end, today
from app.utils.money import ZERO, money
from app.utils.numbering import next_number

logger = logging.getLogger("brightloop.billing")

# Safety cap on catch-up periods per subscription per run; the rest are billed next run.
MAX_PERIODS_PER_RUN = 366


def _line_description(sub_line) -> str:
    text = sub_line.product.name
    if sub_line.variant:
        text += f" ({sub_line.variant.attribute}: {sub_line.variant.value})"
    return text


def build_invoice(db: Session, sub: Subscription, period_start: date, on_date: date) -> Invoice:
    """Create (but do not commit) the invoice for one billing period of a subscription."""
    plan = sub.plan
    drafts: list[DraftLine] = []
    if plan.price > 0:
        drafts.append(
            DraftLine(description=f"Plan: {plan.name} ({plan.billing_period.value.lower()})", quantity=1, unit_price=plan.price)
        )
    for l in sub.lines:
        drafts.append(
            DraftLine(
                description=_line_description(l),
                quantity=l.quantity,
                unit_price=l.unit_price,
                product_id=l.product_id,
                tax=l.tax,
            )
        )

    apply_discounts(db, drafts, on_date)

    lines, subtotal, discount_total, tax_total = [], ZERO, ZERO, ZERO
    for d in drafts:
        tax_amount = line_tax(d.tax, d.net, d.quantity)
        description = d.description + (f" - discount: {', '.join(d.discount_names)}" if d.discount_names else "")
        lines.append(
            InvoiceLine(
                product_id=d.product_id,
                description=description[:255],
                quantity=d.quantity,
                unit_price=d.unit_price,
                discount_amount=money(d.discount),
                tax_amount=tax_amount,
                amount=money(d.net + tax_amount),
            )
        )
        subtotal += d.gross
        discount_total += d.discount
        tax_total += tax_amount

    invoice = Invoice(
        number=next_number(db, "INV"),
        subscription_id=sub.id,
        customer_id=sub.customer_id,
        billing_period_start=period_start,
        billing_period_end=period_end(period_start, plan.billing_period),
        subtotal=money(subtotal),
        discount_total=money(discount_total),
        tax_total=money(tax_total),
        total=money(subtotal - discount_total + tax_total),
        amount_paid=ZERO,
        status=InvoiceStatus.DRAFT,
        due_date=period_start + timedelta(days=sub.payment_terms),
        lines=lines,
    )
    db.add(invoice)
    return invoice


def _bill_subscription(db: Session, subscription_id: int, on_date: date) -> list[str]:
    """Bill every due period of one subscription inside one transaction."""
    # Row lock: a concurrent run waits here, then sees the advanced next_billing_date.
    sub = db.scalars(select(Subscription).where(Subscription.id == subscription_id).with_for_update()).one_or_none()
    if not sub or sub.status != SubscriptionStatus.ACTIVE or not sub.next_billing_date:
        return []

    created = []
    periods = 0
    while sub.next_billing_date <= on_date and periods < MAX_PERIODS_PER_RUN:
        period_start = sub.next_billing_date
        already = db.scalar(
            select(Invoice.id).where(Invoice.subscription_id == sub.id, Invoice.billing_period_start == period_start)
        )
        if not already:
            created.append(build_invoice(db, sub, period_start, on_date).number)
        sub.next_billing_date = add_period(period_start, sub.plan.billing_period)
        periods += 1
    db.commit()
    return created


def generate_due_invoices(db: Session, on_date: date | None = None) -> dict:
    """Invoice every ACTIVE subscription whose next_billing_date <= on_date.

    Safe to run any number of times: each period is billed exactly once
    (row lock + existence check + UNIQUE(subscription_id, billing_period_start)).
    Subscriptions on PAUSED plans are left until the plan is renewed.
    """
    on_date = on_date or today()
    due_ids = db.scalars(
        select(Subscription.id)
        .join(Plan, Plan.id == Subscription.plan_id)
        .where(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.next_billing_date <= on_date,
            Plan.status != PlanStatus.PAUSED,
        )
        .order_by(Subscription.id)
    ).all()
    db.rollback()  # end the read transaction before taking row locks

    created, failed = [], []
    for sub_id in due_ids:
        try:
            created.extend(_bill_subscription(db, sub_id, on_date))
        except Exception:
            db.rollback()
            logger.exception("Billing failed for subscription %s", sub_id)
            failed.append(sub_id)

    logger.info("Billing run for %s: %d invoices created, %d failures", on_date, len(created), len(failed))
    return {
        "date": on_date.isoformat(),
        "subscriptions_checked": len(due_ids),
        "invoices_created": len(created),
        "invoice_numbers": created,
        "failed_subscription_ids": failed,
    }
