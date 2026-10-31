from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value) -> Decimal:
    """Round any number to 2 decimal places, half-up."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
