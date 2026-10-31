from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, computed_field

from app.schemas import ORMModel
from app.schemas.subscription import CustomerRef
from app.services.invoice_service import is_overdue
from app.utils.constants import InvoiceStatus, PaymentMethod


class InvoiceLineOut(ORMModel):
    id: int
    product_id: int | None
    description: str
    quantity: int
    unit_price: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    amount: Decimal


class InvoiceSummaryOut(ORMModel):
    id: int
    number: str
    subscription_id: int
    customer: CustomerRef
    billing_period_start: date
    billing_period_end: date
    subtotal: Decimal
    tax_total: Decimal
    discount_total: Decimal
    total: Decimal
    amount_paid: Decimal
    status: InvoiceStatus
    due_date: date
    sent_at: datetime | None

    @computed_field
    @property
    def balance(self) -> Decimal:
        return self.total - self.amount_paid

    @computed_field
    @property
    def overdue(self) -> bool:
        return is_overdue(self)


class PaymentOut(ORMModel):
    id: int
    invoice_id: int
    method: PaymentMethod
    amount: Decimal
    payment_date: date
    note: str | None


class InvoiceOut(InvoiceSummaryOut):
    lines: list[InvoiceLineOut]
    payments: list[PaymentOut]


class PaymentIn(BaseModel):
    invoice_id: int
    method: PaymentMethod
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payment_date: date | None = None
    note: str | None = Field(default=None, max_length=255)


class GenerateDueIn(BaseModel):
    on_date: date | None = None


class ReportSummaryOut(BaseModel):
    active_subscriptions: int
    revenue_received: Decimal
    outstanding_amount: Decimal
    open_invoices: int
    overdue_amount: Decimal
    overdue_invoices: int


class RevenueRowOut(BaseModel):
    month: str
    amount: Decimal
    payments: int


class OverdueInvoiceOut(InvoiceSummaryOut):
    days_overdue: int = 0
