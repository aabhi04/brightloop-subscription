from decimal import Decimal

from app.models import Tax
from app.utils.constants import TaxType
from app.utils.money import ZERO, money


def line_tax(tax: Tax | None, net_amount: Decimal, quantity: int) -> Decimal:
    """Tax for one invoice line.

    PERCENT: rate% of the line's net amount (after discounts).
    FIXED:   rate per unit, times quantity.
    Inactive or missing taxes add nothing.
    """
    if tax is None or not tax.is_active or net_amount <= 0:
        return ZERO
    if tax.type == TaxType.PERCENT:
        return money(net_amount * tax.rate / 100)
    return money(tax.rate * quantity)
