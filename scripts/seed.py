"""Reset the database and load demo data.

Run from the project root:  python -m scripts.seed
All dates are relative to today, so the demo always has a current, a paid
and an overdue invoice.
"""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select, text

from app import models  # noqa: F401
from app.db import Base, SessionLocal
from app.models import Discount, Invoice, Plan, Product, ProductVariant, QuotationTemplate, QuotationTemplateLine, Tax
from app.services import billing_service, invoice_service, payment_service, subscription_service
from app.services.auth_service import create_user
from app.utils.constants import (
    BillingPeriod,
    DiscountScope,
    DiscountType,
    InvoiceStatus,
    PaymentMethod,
    Role,
    SubscriptionStatus,
    TaxType,
)
from app.utils.dates import add_months, today

CREDENTIALS = [
    ("Asha Admin", "admin@brightloop.local", "Admin@1234", Role.ADMIN),
    ("Sam Staff", "staff@brightloop.local", "Staff@1234", Role.STAFF),
    ("Priya Sharma", "priya@example.com", "Customer@1", Role.CUSTOMER),
    ("Rahul Verma", "rahul@example.com", "Customer@2", Role.CUSTOMER),
]

LIFECYCLE = [SubscriptionStatus.QUOTATION, SubscriptionStatus.CONFIRMED, SubscriptionStatus.ACTIVE]


def reset(db) -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    db.commit()


def advance(db, sub, target: SubscriptionStatus):
    """Walk a subscription through the lifecycle up to `target`."""
    order = [SubscriptionStatus.DRAFT, *LIFECYCLE, SubscriptionStatus.CLOSED]
    while sub.status != target:
        sub = subscription_service.change_status(db, sub.id, order[order.index(sub.status) + 1])
    return sub


def invoices_of(db, sub) -> list[Invoice]:
    return list(db.scalars(select(Invoice).where(Invoice.subscription_id == sub.id).order_by(Invoice.billing_period_start)))


def seed() -> None:
    db = SessionLocal()
    reset(db)
    t = today()

    # ---- Users
    users = {}
    for name, email, password, role in CREDENTIALS:
        users[email] = create_user(db, name, email, password, role)
    db.commit()
    priya, rahul = users["priya@example.com"], users["rahul@example.com"]

    # ---- Taxes
    gst = Tax(name="GST 18%", type=TaxType.PERCENT, rate=Decimal("18"))
    service_fee = Tax(name="Service Levy (per unit)", type=TaxType.FIXED, rate=Decimal("25"))
    db.add_all([gst, service_fee])

    # ---- Products and variants
    erp = Product(
        name="ERP Suite", type="SERVICE", sales_price=Decimal("1000"), cost_price=Decimal("400"),
        notes="Business management suite",
        variants=[
            ProductVariant(attribute="Brand", value="Odoo", extra_price=Decimal("560")),
            ProductVariant(attribute="Brand", value="SAP", extra_price=Decimal("900")),
        ],
    )
    hosting = Product(
        name="Cloud Hosting", type="SERVICE", sales_price=Decimal("500"), cost_price=Decimal("200"),
        variants=[
            ProductVariant(attribute="Tier", value="Standard", extra_price=Decimal("0")),
            ProductVariant(attribute="Tier", value="Premium", extra_price=Decimal("300")),
        ],
    )
    support = Product(
        name="Support Desk", type="SERVICE", sales_price=Decimal("300"), cost_price=Decimal("100"),
        variants=[
            ProductVariant(attribute="Seats", value="5 seats", extra_price=Decimal("0")),
            ProductVariant(attribute="Seats", value="10 seats", extra_price=Decimal("250")),
        ],
    )
    db.add_all([erp, hosting, support])

    # ---- Plans
    monthly = Plan(name="Monthly Standard", price=Decimal("199"), billing_period=BillingPeriod.MONTHLY,
                   min_quantity=1, start_date=add_months(t, -12))
    yearly = Plan(name="Yearly Pro", price=Decimal("0"), billing_period=BillingPeriod.YEARLY,
                  min_quantity=2, start_date=add_months(t, -12), pausable=False)
    weekly = Plan(name="Weekly Flex", price=Decimal("49"), billing_period=BillingPeriod.WEEKLY,
                  min_quantity=1, start_date=add_months(t, -3), end_date=add_months(t, 6), auto_close=True)
    db.add_all([monthly, yearly, weekly])

    # ---- Discount (subscription-level, currently active)
    db.add(Discount(
        name="Welcome 10%", type=DiscountType.PERCENT, value=Decimal("10"), min_purchase=Decimal("500"),
        min_quantity=0, start_date=t - timedelta(days=90), end_date=t + timedelta(days=90),
        usage_limit=100, applies_to=DiscountScope.SUBSCRIPTION,
    ))
    db.commit()
    odoo, sap = erp.variants
    premium = hosting.variants[1]
    five_seats = support.variants[0]

    # ---- Quotation template
    template = QuotationTemplate(
        name="ERP Starter Pack", validity_days=30, plan_id=monthly.id,
        lines=[
            QuotationTemplateLine(product_id=erp.id, variant_id=odoo.id, quantity=1),
            QuotationTemplateLine(product_id=support.id, variant_id=five_seats.id, quantity=1),
        ],
    )
    db.add(template)
    db.commit()

    def create(customer, plan, start, lines):
        return subscription_service.create_subscription(
            db, customer_id=customer.id, plan_id=plan.id, start_date=start, expiry_date=None,
            payment_terms=15, lines=lines,
        )

    # ---- Subscriptions across every status
    # 1. Priya, ACTIVE monthly since 2 months ago -> 3 billed periods
    s1 = create(priya, monthly, add_months(t, -2), [
        {"product_id": erp.id, "variant_id": odoo.id, "quantity": 2, "tax_id": gst.id},
        {"product_id": hosting.id, "variant_id": premium.id, "quantity": 1, "tax_id": service_fee.id},
    ])
    advance(db, s1, SubscriptionStatus.ACTIVE)
    # 2. Rahul, ACTIVE weekly since 2 weeks ago -> 3 billed periods
    s2 = create(rahul, weekly, t - timedelta(days=14), [
        {"product_id": support.id, "variant_id": five_seats.id, "quantity": 1, "tax_id": gst.id},
    ])
    advance(db, s2, SubscriptionStatus.ACTIVE)
    # 3. Priya, weekly, will be CLOSED after billing
    s3 = create(priya, weekly, t - timedelta(days=7), [
        {"product_id": hosting.id, "variant_id": None, "quantity": 1, "tax_id": None},
    ])
    advance(db, s3, SubscriptionStatus.ACTIVE)
    # 4. Rahul, CONFIRMED yearly starting next week
    s4 = create(rahul, yearly, t + timedelta(days=7), [
        {"product_id": erp.id, "variant_id": sap.id, "quantity": 2, "tax_id": gst.id},
    ])
    advance(db, s4, SubscriptionStatus.CONFIRMED)
    # 5. Priya, QUOTATION from the template
    subscription_service.create_from_template(db, template.id, priya.id)
    # 6. Rahul, DRAFT
    create(rahul, monthly, t, [{"product_id": hosting.id, "variant_id": None, "quantity": 1, "tax_id": gst.id}])

    # ---- Billing (same service as the API and the cron job)
    result = billing_service.generate_due_invoices(db, t)

    # ---- Invoice states and payments
    i1 = invoices_of(db, s1)  # [2 months ago, 1 month ago, current]
    invoice_service.confirm_invoice(db, i1[0].id)
    payment_service.record_payment(db, invoice_id=i1[0].id, method=PaymentMethod.BANK_TRANSFER,
                                   amount=i1[0].total, payment_date=i1[0].billing_period_start + timedelta(days=5),
                                   note="Paid in full")
    invoice_service.confirm_invoice(db, i1[1].id)  # due ~2 weeks ago -> OVERDUE after a partial payment
    payment_service.record_payment(db, invoice_id=i1[1].id, method=PaymentMethod.UPI, amount=Decimal("1000"),
                                   payment_date=i1[1].billing_period_start + timedelta(days=3), note="Partial payment")
    # i1[2] stays DRAFT

    i2 = invoices_of(db, s2)
    invoice_service.confirm_invoice(db, i2[0].id)
    payment_service.record_payment(db, invoice_id=i2[0].id, method=PaymentMethod.CARD, amount=i2[0].total,
                                   payment_date=i2[0].billing_period_start + timedelta(days=1))
    invoice_service.confirm_invoice(db, i2[1].id)  # open, not yet due
    invoice_service.send_invoice(db, i2[1].id)

    for inv in invoices_of(db, s3):
        invoice_service.cancel_invoice(db, inv.id)
    advance(db, subscription_service.get_subscription(db, s3.id), SubscriptionStatus.CLOSED)

    counts = {s.value: 0 for s in InvoiceStatus}
    for inv in db.scalars(select(Invoice)):
        counts[inv.status.value] += 1
    overdue = db.scalar(select(text("count(*)")).select_from(Invoice).where(invoice_service.overdue_condition()))
    db.close()

    print(f"\nSeed complete: {result['invoices_created']} invoices generated; by status {counts}; overdue: {overdue}")
    print("\nLogin credentials:")
    for name, email, password, role in CREDENTIALS:
        print(f"  {role.value:<9} {email:<26} {password}")


if __name__ == "__main__":
    seed()
