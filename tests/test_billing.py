from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import Invoice
from app.services import billing_service, invoice_service, payment_service, subscription_service
from app.utils.constants import InvoiceStatus, PaymentMethod, Role, SubscriptionStatus
from app.utils.dates import add_months
from app.utils.errors import AppError
from tests.conftest import auth


def invoice_count(db) -> int:
    return db.scalar(select(func.count(Invoice.id)))


def test_generate_due_twice_creates_no_duplicates(client, db, make_user, active_subscription):
    staff = make_user(Role.STAFF)
    customer = make_user(Role.CUSTOMER)
    active_subscription(customer, date.today())
    active_subscription(customer, date.today() - timedelta(days=3))

    first = client.post("/api/invoices/generate-due", headers=auth(staff))
    assert first.status_code == 200
    assert first.json()["invoices_created"] == 2

    second = client.post("/api/invoices/generate-due", headers=auth(staff))
    assert second.json()["invoices_created"] == 0
    assert invoice_count(db) == 2

    # No two invoices for the same subscription and period
    pairs = db.execute(select(Invoice.subscription_id, Invoice.billing_period_start)).all()
    assert len(pairs) == len(set(pairs))


def test_catch_up_bills_every_missed_period_and_skips_nothing(db, make_user, active_subscription):
    customer = make_user(Role.CUSTOMER)
    start = add_months(date.today(), -3)
    sub = active_subscription(customer, start)

    result = billing_service.generate_due_invoices(db)
    assert result["invoices_created"] == 4  # start, +1, +2, +3 months (today)
    starts = sorted(db.scalars(select(Invoice.billing_period_start).where(Invoice.subscription_id == sub.id)))
    assert starts == [add_months(start, n) for n in range(4)]

    # Periods are contiguous: each ends the day before the next starts
    invoices = sorted(db.scalars(select(Invoice)), key=lambda i: i.billing_period_start)
    for current, nxt in zip(invoices, invoices[1:]):
        assert current.billing_period_end + timedelta(days=1) == nxt.billing_period_start

    db.expire_all()
    assert subscription_service.get_subscription(db, sub.id).next_billing_date == add_months(start, 4)
    assert billing_service.generate_due_invoices(db)["invoices_created"] == 0


def test_only_active_and_due_subscriptions_are_billed(db, make_user, catalog, active_subscription):
    customer = make_user(Role.CUSTOMER)
    active_subscription(customer, date.today() + timedelta(days=5))  # not yet due
    subscription_service.create_subscription(  # DRAFT
        db, customer_id=customer.id, plan_id=catalog["plan"].id, start_date=date.today(), expiry_date=None,
        payment_terms=15, lines=[{"product_id": catalog["product"].id, "quantity": 1}],
    )
    assert billing_service.generate_due_invoices(db)["invoices_created"] == 0


def test_database_rejects_duplicate_period(db, make_user, active_subscription):
    customer = make_user(Role.CUSTOMER)
    sub = active_subscription(customer, date.today())
    billing_service.generate_due_invoices(db)
    existing = db.scalars(select(Invoice)).one()
    db.add(Invoice(
        number="INV-9999", subscription_id=sub.id, customer_id=customer.id,
        billing_period_start=existing.billing_period_start, billing_period_end=existing.billing_period_end,
        subtotal=0, total=0, due_date=existing.due_date,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_invoice_totals_use_variant_price_and_line_tax(db, make_user, active_subscription):
    customer = make_user(Role.CUSTOMER)
    active_subscription(customer, date.today(), quantity=2)
    billing_service.generate_due_invoices(db)
    invoice = db.scalars(select(Invoice)).one()

    line = invoice.lines[0]
    assert line.unit_price == Decimal("1560.00")  # 1000 + Odoo 560
    assert invoice.subtotal == Decimal("3120.00")
    assert invoice.tax_total == Decimal("561.60")  # 18% of 3120
    assert invoice.total == Decimal("3681.60")
    assert invoice.status == InvoiceStatus.DRAFT
    assert invoice.due_date == invoice.billing_period_start + timedelta(days=15)


def test_partial_payments_then_paid(db, make_user, active_subscription):
    customer = make_user(Role.CUSTOMER)
    active_subscription(customer, date.today())
    billing_service.generate_due_invoices(db)
    invoice = db.scalars(select(Invoice)).one()

    with pytest.raises(AppError, match="Confirm the invoice"):
        payment_service.record_payment(db, invoice_id=invoice.id, method=PaymentMethod.CASH,
                                       amount=Decimal("10"), payment_date=date.today())
    invoice_service.confirm_invoice(db, invoice.id)

    payment_service.record_payment(db, invoice_id=invoice.id, method=PaymentMethod.UPI,
                                   amount=Decimal("1000"), payment_date=date.today())
    db.refresh(invoice)
    assert invoice.status == InvoiceStatus.CONFIRMED
    assert invoice.amount_paid == Decimal("1000.00")

    with pytest.raises(AppError, match="exceeds the outstanding balance"):
        payment_service.record_payment(db, invoice_id=invoice.id, method=PaymentMethod.UPI,
                                       amount=invoice.total, payment_date=date.today())

    payment_service.record_payment(db, invoice_id=invoice.id, method=PaymentMethod.CARD,
                                   amount=invoice.total - Decimal("1000"), payment_date=date.today())
    db.refresh(invoice)
    assert invoice.status == InvoiceStatus.PAID
    assert invoice.balance == Decimal("0.00")


def test_overdue_rule(db, make_user, active_subscription):
    customer = make_user(Role.CUSTOMER)
    active_subscription(customer, date.today() - timedelta(days=20))  # due 5 days ago
    billing_service.generate_due_invoices(db, date.today() - timedelta(days=20))
    invoice = db.scalars(select(Invoice)).one()

    assert not invoice_service.is_overdue(invoice)  # DRAFT is never overdue
    invoice_service.confirm_invoice(db, invoice.id)
    db.refresh(invoice)
    assert invoice_service.is_overdue(invoice)
    assert db.scalar(select(func.count(Invoice.id)).where(invoice_service.overdue_condition())) == 1

    payment_service.record_payment(db, invoice_id=invoice.id, method=PaymentMethod.CASH,
                                   amount=invoice.total, payment_date=date.today())
    db.refresh(invoice)
    assert not invoice_service.is_overdue(invoice)


def test_invalid_subscription_transition_returns_400(client, db, make_user, catalog):
    staff = make_user(Role.STAFF)
    customer = make_user(Role.CUSTOMER)
    sub = subscription_service.create_subscription(
        db, customer_id=customer.id, plan_id=catalog["plan"].id, start_date=date.today(), expiry_date=None,
        payment_terms=15, lines=[{"product_id": catalog["product"].id, "quantity": 1}],
    )
    r = client.patch(f"/api/subscriptions/{sub.id}/status", headers=auth(staff), json={"status": "ACTIVE"})
    assert r.status_code == 400
    assert r.json()["error"] == "Invalid status change DRAFT -> ACTIVE. Allowed next status: QUOTATION"
    assert subscription_service.get_subscription(db, sub.id).status == SubscriptionStatus.DRAFT
