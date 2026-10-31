from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models import Discount, Invoice
from app.services import billing_service
from app.utils.constants import DiscountScope, DiscountType, Role


def add_discount(db, **overrides) -> Discount:
    today = date.today()
    values = dict(
        name="10% off", type=DiscountType.PERCENT, value=Decimal("10"), min_purchase=Decimal("0"),
        min_quantity=0, start_date=today - timedelta(days=1), end_date=today + timedelta(days=30),
        usage_limit=10, applies_to=DiscountScope.SUBSCRIPTION,
    )
    values.update(overrides)
    products = values.pop("products", [])
    discount = Discount(**values, products=products)
    db.add(discount)
    db.commit()
    return discount


def invoices_by_customer(db, customer) -> list[Invoice]:
    return list(db.scalars(select(Invoice).where(Invoice.customer_id == customer.id).order_by(Invoice.id)))


def test_discount_applies_when_eligible(db, make_user, active_subscription):
    discount = add_discount(db)
    customer = make_user(Role.CUSTOMER)
    active_subscription(customer, date.today())  # 1 x 1560, 18% tax
    billing_service.generate_due_invoices(db)

    invoice = invoices_by_customer(db, customer)[0]
    assert invoice.discount_total == Decimal("156.00")
    assert invoice.tax_total == Decimal("252.72")  # 18% of (1560 - 156): tax is on the discounted amount
    assert invoice.total == Decimal("1656.72")
    db.refresh(discount)
    assert discount.used_count == 1


def test_discount_stops_after_usage_limit(db, make_user, active_subscription):
    discount = add_discount(db, usage_limit=1)
    first, second = make_user(Role.CUSTOMER), make_user(Role.CUSTOMER)
    active_subscription(first, date.today())
    active_subscription(second, date.today())
    billing_service.generate_due_invoices(db)

    assert invoices_by_customer(db, first)[0].discount_total == Decimal("156.00")
    assert invoices_by_customer(db, second)[0].discount_total == Decimal("0.00")
    db.refresh(discount)
    assert discount.used_count == 1


def test_usage_limit_holds_across_catch_up_periods(db, make_user, active_subscription):
    discount = add_discount(db, usage_limit=2, start_date=date.today() - timedelta(days=120))
    customer = make_user(Role.CUSTOMER)
    active_subscription(customer, date.today() - timedelta(days=95))  # 4 monthly periods due
    billing_service.generate_due_invoices(db)

    discounted = [i for i in invoices_by_customer(db, customer) if i.discount_total > 0]
    assert len(invoices_by_customer(db, customer)) == 4
    assert len(discounted) == 2
    db.refresh(discount)
    assert discount.used_count == 2


def test_expired_or_future_discount_is_not_applied(db, make_user, active_subscription):
    today = date.today()
    expired = add_discount(db, name="old", start_date=today - timedelta(days=30), end_date=today - timedelta(days=1))
    future = add_discount(db, name="soon", start_date=today + timedelta(days=1), end_date=today + timedelta(days=30))
    customer = make_user(Role.CUSTOMER)
    active_subscription(customer, today)
    billing_service.generate_due_invoices(db)

    assert invoices_by_customer(db, customer)[0].discount_total == Decimal("0.00")
    db.refresh(expired)
    db.refresh(future)
    assert expired.used_count == 0 and future.used_count == 0


def test_min_purchase_and_min_quantity_must_be_met(db, make_user, active_subscription):
    add_discount(db, name="big spenders", min_purchase=Decimal("5000"))
    add_discount(db, name="bulk", min_quantity=3)
    customer = make_user(Role.CUSTOMER)
    active_subscription(customer, date.today(), quantity=2)  # 3120 total, qty 2
    billing_service.generate_due_invoices(db)
    assert invoices_by_customer(db, customer)[0].discount_total == Decimal("0.00")


def test_product_discount_applies_only_to_matching_lines(db, make_user, catalog, active_subscription):
    add_discount(
        db, name="Hosting 100 off", type=DiscountType.FIXED, value=Decimal("100"),
        applies_to=DiscountScope.PRODUCT, products=[catalog["other"]],
    )
    erp_customer, hosting_customer = make_user(Role.CUSTOMER), make_user(Role.CUSTOMER)
    active_subscription(erp_customer, date.today())
    active_subscription(hosting_customer, date.today(), product=catalog["other"])
    billing_service.generate_due_invoices(db)

    assert invoices_by_customer(db, erp_customer)[0].discount_total == Decimal("0.00")
    hosting_invoice = invoices_by_customer(db, hosting_customer)[0]
    assert hosting_invoice.discount_total == Decimal("100.00")
    assert hosting_invoice.lines[0].discount_amount == Decimal("100.00")
