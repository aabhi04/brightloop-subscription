import calendar
from datetime import date, timedelta

from app.utils.constants import BillingPeriod


def today() -> date:
    return date.today()


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def add_period(d: date, period: BillingPeriod, count: int = 1) -> date:
    if period == BillingPeriod.DAILY:
        return d + timedelta(days=count)
    if period == BillingPeriod.WEEKLY:
        return d + timedelta(weeks=count)
    if period == BillingPeriod.MONTHLY:
        return add_months(d, count)
    if period == BillingPeriod.YEARLY:
        return add_months(d, 12 * count)
    raise ValueError(f"Unknown billing period: {period}")


def period_end(start: date, period: BillingPeriod) -> date:
    """Last day covered by a billing period that starts on `start`."""
    return add_period(start, period) - timedelta(days=1)
