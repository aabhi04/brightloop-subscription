import enum


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    STAFF = "STAFF"
    CUSTOMER = "CUSTOMER"


class BillingPeriod(str, enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


class PlanStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"


class SubscriptionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    QUOTATION = "QUOTATION"
    CONFIRMED = "CONFIRMED"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class TaxType(str, enum.Enum):
    PERCENT = "PERCENT"
    FIXED = "FIXED"


class DiscountType(str, enum.Enum):
    FIXED = "FIXED"
    PERCENT = "PERCENT"


class DiscountScope(str, enum.Enum):
    PRODUCT = "PRODUCT"
    SUBSCRIPTION = "SUBSCRIPTION"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class PaymentMethod(str, enum.Enum):
    CASH = "CASH"
    CARD = "CARD"
    BANK_TRANSFER = "BANK_TRANSFER"
    UPI = "UPI"


# Allowed subscription status moves: current -> next
SUBSCRIPTION_TRANSITIONS = {
    SubscriptionStatus.DRAFT: {SubscriptionStatus.QUOTATION},
    SubscriptionStatus.QUOTATION: {SubscriptionStatus.CONFIRMED},
    SubscriptionStatus.CONFIRMED: {SubscriptionStatus.ACTIVE},
    SubscriptionStatus.ACTIVE: {SubscriptionStatus.CLOSED},
    SubscriptionStatus.CLOSED: set(),
}

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
