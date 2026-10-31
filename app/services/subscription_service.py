from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Plan,
    Product,
    ProductVariant,
    QuotationTemplate,
    Subscription,
    SubscriptionLine,
    Tax,
    User,
)
from app.utils.constants import SUBSCRIPTION_TRANSITIONS, PlanStatus, Role, SubscriptionStatus
from app.utils.dates import today
from app.utils.errors import AppError, NotFound, get_or_404
from app.utils.money import money
from app.utils.numbering import next_number

EDITABLE_STATUSES = {SubscriptionStatus.DRAFT, SubscriptionStatus.QUOTATION}


def resolve_product_and_variant(
    db: Session, product_id: int, variant_id: int | None
) -> tuple[Product, ProductVariant | None]:
    product = get_or_404(db, Product, product_id)
    variant = None
    if variant_id is not None:
        variant = db.get(ProductVariant, variant_id)
        if not variant or variant.product_id != product.id:
            raise AppError(f"Variant {variant_id} does not belong to product '{product.name}'")
    return product, variant


def unit_price_for(product: Product, variant: ProductVariant | None) -> Decimal:
    """Variant pricing rule: product sales price + variant extra price."""
    return money(product.sales_price + (variant.extra_price if variant else 0))


def build_line(db: Session, product_id: int, variant_id: int | None, quantity: int, tax_id: int | None) -> SubscriptionLine:
    if quantity < 1:
        raise AppError("Quantity must be at least 1")
    product, variant = resolve_product_and_variant(db, product_id, variant_id)
    if tax_id is not None:
        tax = db.get(Tax, tax_id)
        if not tax:
            raise AppError(f"Tax {tax_id} not found")
        if not tax.is_active:
            raise AppError(f"Tax '{tax.name}' is not active")
    unit_price = unit_price_for(product, variant)
    return SubscriptionLine(
        product_id=product.id,
        variant_id=variant.id if variant else None,
        quantity=quantity,
        unit_price=unit_price,
        tax_id=tax_id,
        amount=money(unit_price * quantity),
    )


def _check_customer(db: Session, customer_id: int) -> User:
    customer = db.get(User, customer_id)
    if not customer or customer.role != Role.CUSTOMER:
        raise AppError("customer_id must refer to an existing CUSTOMER user")
    return customer


def _check_plan_open(db: Session, plan_id: int) -> Plan:
    plan = get_or_404(db, Plan, plan_id)
    if plan.status == PlanStatus.CLOSED:
        raise AppError(f"Plan '{plan.name}' is closed")
    return plan


def subscription_list_query(
    status: SubscriptionStatus | None = None,
    customer_id: int | None = None,
    plan_id: int | None = None,
    q: str | None = None,
    start_from: date | None = None,
    start_to: date | None = None,
):
    """Shared filters for the staff list and the customer portal."""
    stmt = (
        select(Subscription)
        .options(joinedload(Subscription.customer), joinedload(Subscription.plan))
        .order_by(Subscription.id.desc())
    )
    if status:
        stmt = stmt.where(Subscription.status == status)
    if customer_id:
        stmt = stmt.where(Subscription.customer_id == customer_id)
    if plan_id:
        stmt = stmt.where(Subscription.plan_id == plan_id)
    if q:
        stmt = stmt.where(Subscription.number.ilike(f"%{q}%"))
    if start_from:
        stmt = stmt.where(Subscription.start_date >= start_from)
    if start_to:
        stmt = stmt.where(Subscription.start_date <= start_to)
    return stmt


def get_subscription(db: Session, subscription_id: int) -> Subscription:
    sub = db.get(Subscription, subscription_id)
    if not sub:
        raise NotFound("Subscription")
    return sub


def create_subscription(
    db: Session,
    *,
    customer_id: int,
    plan_id: int,
    start_date: date,
    expiry_date: date | None,
    payment_terms: int,
    lines: list[dict],
    status: SubscriptionStatus = SubscriptionStatus.DRAFT,
) -> Subscription:
    _check_customer(db, customer_id)
    _check_plan_open(db, plan_id)
    sub = Subscription(
        number=next_number(db, "SUB"),
        customer_id=customer_id,
        plan_id=plan_id,
        start_date=start_date,
        expiry_date=expiry_date,
        payment_terms=payment_terms,
        status=status,
        lines=[build_line(db, l["product_id"], l.get("variant_id"), l["quantity"], l.get("tax_id")) for l in lines],
    )
    db.add(sub)
    db.commit()
    return sub


def update_subscription(
    db: Session,
    subscription_id: int,
    *,
    customer_id: int,
    plan_id: int,
    start_date: date,
    expiry_date: date | None,
    payment_terms: int,
    lines: list[dict],
) -> Subscription:
    sub = get_subscription(db, subscription_id)
    if sub.status not in EDITABLE_STATUSES:
        raise AppError(f"Only DRAFT or QUOTATION subscriptions can be edited (current status: {sub.status.value})")
    _check_customer(db, customer_id)
    _check_plan_open(db, plan_id)
    sub.customer_id = customer_id
    sub.plan_id = plan_id
    sub.start_date = start_date
    sub.expiry_date = expiry_date
    sub.payment_terms = payment_terms
    sub.lines = [build_line(db, l["product_id"], l.get("variant_id"), l["quantity"], l.get("tax_id")) for l in lines]
    db.commit()
    return sub


def delete_subscription(db: Session, subscription_id: int) -> None:
    sub = get_subscription(db, subscription_id)
    if sub.status not in EDITABLE_STATUSES:
        raise AppError("Only DRAFT or QUOTATION subscriptions can be deleted; close it instead")
    db.delete(sub)
    db.commit()


def create_from_template(
    db: Session, template_id: int, customer_id: int, start_date: date | None = None, payment_terms: int = 15
) -> Subscription:
    """Copy plan and lines from a template into a new QUOTATION, valid for `validity_days`."""
    template = get_or_404(db, QuotationTemplate, template_id, "Quotation template")
    # Template lines carry no tax; staff can add taxes while the quotation is editable.
    lines = [
        {"product_id": l.product_id, "variant_id": l.variant_id, "quantity": l.quantity, "tax_id": None}
        for l in template.lines
    ]
    return create_subscription(
        db,
        customer_id=customer_id,
        plan_id=template.plan_id,
        start_date=start_date or today(),
        expiry_date=today() + timedelta(days=template.validity_days),
        payment_terms=payment_terms,
        lines=lines,
        status=SubscriptionStatus.QUOTATION,
    )


def change_status(db: Session, subscription_id: int, new_status: SubscriptionStatus) -> Subscription:
    sub = get_subscription(db, subscription_id)
    allowed = SUBSCRIPTION_TRANSITIONS[sub.status]
    if new_status not in allowed:
        nxt = ", ".join(s.value for s in allowed) or "none (final state)"
        raise AppError(
            f"Invalid status change {sub.status.value} -> {new_status.value}. Allowed next status: {nxt}"
        )

    plan = sub.plan
    if new_status == SubscriptionStatus.CONFIRMED:
        if not sub.lines:
            raise AppError("Add at least one product line before confirming")
        total_qty = sum(l.quantity for l in sub.lines)
        if total_qty < plan.min_quantity:
            raise AppError(f"Plan '{plan.name}' requires a total quantity of at least {plan.min_quantity}")
        if sub.expiry_date and sub.expiry_date < today():
            raise AppError(f"Quotation expired on {sub.expiry_date.isoformat()}")
        if plan.status != PlanStatus.ACTIVE:
            raise AppError(f"Plan '{plan.name}' is {plan.status.value}; cannot confirm")
    elif new_status == SubscriptionStatus.ACTIVE:
        if plan.status == PlanStatus.CLOSED:
            raise AppError(f"Plan '{plan.name}' is closed; cannot activate")
        sub.next_billing_date = sub.next_billing_date or sub.start_date
    elif new_status == SubscriptionStatus.CLOSED:
        if not plan.closable:
            raise AppError(f"Plan '{plan.name}' does not allow closing subscriptions")
        sub.next_billing_date = None

    sub.status = new_status
    db.commit()
    return sub
