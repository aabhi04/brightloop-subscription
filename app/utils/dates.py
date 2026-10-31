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


def next_period_start(anchor: date, current: date, period: BillingPeriod) -> date:
    """Start of the period after `current`, keeping the anchor's day of month.

    Stepping month by month from the previous date drifts (Aug 31 -> Sep 30 -> Oct 30);
    counting months from the anchor gives Aug 31 -> Sep 30 -> Oct 31.
    """
    if period in (BillingPeriod.MONTHLY, BillingPeriod.YEARLY):
        step = 1 if period == BillingPeriod.MONTHLY else 12
        months = (current.year - anchor.year) * 12 + (current.month - anchor.month)
        return add_months(anchor, months + step)
    return add_period(current, period)
