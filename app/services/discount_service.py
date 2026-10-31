from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Discount
from app.utils.constants import DiscountScope, DiscountType
from app.utils.money import ZERO, money


@dataclass
class DraftLine:
    """An invoice line while totals are being worked out."""

    description: str
    quantity: int
    unit_price: Decimal
    product_id: int | None = None
    tax: object = None
    discount: Decimal = ZERO
    discount_names: list[str] = field(default_factory=list)

    @property
    def gross(self) -> Decimal:
        return money(self.unit_price * self.quantity)

    @property
    def net(self) -> Decimal:
        return self.gross - self.discount


def active_discounts(db: Session, on_date: date, scope: DiscountScope, lock: bool = True) -> list[Discount]:
    """Discounts valid on `on_date` that still have uses left.

    Rows are locked (FOR UPDATE, in id order) so two billing runs cannot both use
    the last remaining use of a discount.
    """
    stmt = (
        select(Discount)
        .options(selectinload(Discount.products))
        .where(
            Discount.applies_to == scope,
            Discount.start_date <= on_date,
            Discount.end_date >= on_date,
            Discount.used_count < Discount.usage_limit,
        )
        .order_by(Discount.id)
    )
    if lock:
        stmt = stmt.with_for_update()
    return list(db.scalars(stmt).all())


def discount_value(discount: Discount, base: Decimal) -> Decimal:
    if base <= 0:
        return ZERO
    if discount.type == DiscountType.PERCENT:
        amount = money(base * discount.value / 100)
    else:
        amount = money(discount.value)
    return min(amount, base)


def apply_discounts(db: Session, lines: list[DraftLine], on_date: date) -> list[Discount]:
    """Apply eligible discounts to the draft lines in place and return the discounts used.

    - PRODUCT discounts: each matching line gets the best eligible one
      (line gross >= min_purchase and line quantity >= min_quantity).
    - SUBSCRIPTION discounts: the best eligible one (invoice gross >= min_purchase and
      total quantity >= min_quantity) is spread across lines in proportion to their net.
    Each discount used has used_count incremented once per invoice.
    """
    used: dict[int, Discount] = {}

    product_discounts = active_discounts(db, on_date, DiscountScope.PRODUCT)
    for line in lines:
        if line.product_id is None:
            continue
        best, best_amount = None, ZERO
        for d in product_discounts:
            if line.product_id not in {p.id for p in d.products}:  # products are preloaded
                continue
            if line.gross < d.min_purchase or line.quantity < d.min_quantity:
                continue
            amount = discount_value(d, line.gross)
            if amount > best_amount:
                best, best_amount = d, amount
        if best:
            line.discount += best_amount
            line.discount_names.append(best.name)
            used[best.id] = best

    invoice_gross = sum((l.gross for l in lines), ZERO)
    total_qty = sum(l.quantity for l in lines)
    base = sum((l.net for l in lines), ZERO)
    best, best_amount = None, ZERO
    for d in active_discounts(db, on_date, DiscountScope.SUBSCRIPTION):
        if invoice_gross < d.min_purchase or total_qty < d.min_quantity:
            continue
        amount = discount_value(d, base)
        if amount > best_amount:
            best, best_amount = d, amount
    if best:
        _allocate(lines, best_amount, best.name)
        used[best.id] = best

    for d in used.values():
        d.used_count += 1
    db.flush()  # later periods in the same run must see the new used_count
    return list(used.values())


def _allocate(lines: list[DraftLine], amount: Decimal, name: str) -> None:
    """Split `amount` across lines by net value; rounding remainder goes to the last line."""
    eligible = [l for l in lines if l.net > 0]
    base = sum((l.net for l in eligible), ZERO)
    remaining = amount
    for i, line in enumerate(eligible):
        share = remaining if i == len(eligible) - 1 else money(amount * line.net / base)
        share = min(share, line.net)
        line.discount += share
        line.discount_names.append(name)
        remaining -= share
