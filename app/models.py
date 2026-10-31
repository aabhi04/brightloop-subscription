from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.utils.constants import (
    BillingPeriod,
    DiscountScope,
    DiscountType,
    InvoiceStatus,
    PaymentMethod,
    PlanStatus,
    Role,
    SubscriptionStatus,
    TaxType,
)

Money = Numeric(12, 2)


def pg_enum(enum_cls, name):
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(pg_enum(Role, "role"), default=Role.CUSTOMER, index=True)
    reset_token: Mapped[str | None] = mapped_column(String(128), unique=True)
    reset_token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="customer")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    type: Mapped[str] = mapped_column(String(40), default="SERVICE")
    sales_price: Mapped[Decimal] = mapped_column(Money)
    cost_price: Mapped[Decimal] = mapped_column(Money, default=0)
    notes: Mapped[str | None] = mapped_column(Text)

    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="ProductVariant.id"
    )


class ProductVariant(Base):
    __tablename__ = "product_variants"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    attribute: Mapped[str] = mapped_column(String(80))
    value: Mapped[str] = mapped_column(String(80))
    extra_price: Mapped[Decimal] = mapped_column(Money, default=0)

    product: Mapped[Product] = relationship(back_populates="variants")


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (Index("ix_plans_autoclose", "status", "auto_close", "end_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    price: Mapped[Decimal] = mapped_column(Money, default=0)
    billing_period: Mapped[BillingPeriod] = mapped_column(pg_enum(BillingPeriod, "billing_period"))
    min_quantity: Mapped[int] = mapped_column(Integer, default=1)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    auto_close: Mapped[bool] = mapped_column(Boolean, default=False)
    closable: Mapped[bool] = mapped_column(Boolean, default=True)
    pausable: Mapped[bool] = mapped_column(Boolean, default=True)
    renewable: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[PlanStatus] = mapped_column(pg_enum(PlanStatus, "plan_status"), default=PlanStatus.ACTIVE)


class QuotationTemplate(Base):
    __tablename__ = "quotation_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    validity_days: Mapped[int] = mapped_column(Integer)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))

    plan: Mapped[Plan] = relationship()
    lines: Mapped[list["QuotationTemplateLine"]] = relationship(
        back_populates="template", cascade="all, delete-orphan", order_by="QuotationTemplateLine.id"
    )


class QuotationTemplateLine(Base):
    __tablename__ = "quotation_template_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("quotation_templates.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("product_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    template: Mapped[QuotationTemplate] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()
    variant: Mapped[ProductVariant | None] = relationship()


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    start_date: Mapped[date] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    payment_terms: Mapped[int] = mapped_column(Integer, default=15)  # days until invoice is due
    status: Mapped[SubscriptionStatus] = mapped_column(
        pg_enum(SubscriptionStatus, "subscription_status"), default=SubscriptionStatus.DRAFT, index=True
    )
    next_billing_date: Mapped[date | None] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    customer: Mapped[User] = relationship(back_populates="subscriptions")
    plan: Mapped[Plan] = relationship()
    lines: Mapped[list["SubscriptionLine"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan", order_by="SubscriptionLine.id"
    )


class SubscriptionLine(Base):
    __tablename__ = "subscription_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("product_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Money)  # product.sales_price + variant.extra_price
    tax_id: Mapped[int | None] = mapped_column(ForeignKey("taxes.id"))
    amount: Mapped[Decimal] = mapped_column(Money)  # quantity * unit_price, before tax

    subscription: Mapped[Subscription] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()
    variant: Mapped[ProductVariant | None] = relationship()
    tax: Mapped["Tax | None"] = relationship()


class Tax(Base):
    __tablename__ = "taxes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    type: Mapped[TaxType] = mapped_column(pg_enum(TaxType, "tax_type"))
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Discount(Base):
    __tablename__ = "discounts"
    __table_args__ = (Index("ix_discounts_window", "start_date", "end_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[DiscountType] = mapped_column(pg_enum(DiscountType, "discount_type"))
    value: Mapped[Decimal] = mapped_column(Money)
    min_purchase: Mapped[Decimal] = mapped_column(Money, default=0)
    min_quantity: Mapped[int] = mapped_column(Integer, default=0)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    usage_limit: Mapped[int] = mapped_column(Integer)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    applies_to: Mapped[DiscountScope] = mapped_column(pg_enum(DiscountScope, "discount_scope"))

    products: Mapped[list[Product]] = relationship(secondary="discount_products")


class DiscountProduct(Base):
    __tablename__ = "discount_products"

    discount_id: Mapped[int] = mapped_column(ForeignKey("discounts.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("subscription_id", "billing_period_start", name="uq_invoice_subscription_period"),
        Index("ix_invoices_status_due", "status", "due_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    billing_period_start: Mapped[date] = mapped_column(Date)
    billing_period_end: Mapped[date] = mapped_column(Date)
    subtotal: Mapped[Decimal] = mapped_column(Money)
    tax_total: Mapped[Decimal] = mapped_column(Money, default=0)
    discount_total: Mapped[Decimal] = mapped_column(Money, default=0)
    total: Mapped[Decimal] = mapped_column(Money)
    amount_paid: Mapped[Decimal] = mapped_column(Money, default=0)
    status: Mapped[InvoiceStatus] = mapped_column(
        pg_enum(InvoiceStatus, "invoice_status"), default=InvoiceStatus.DRAFT, index=True
    )
    due_date: Mapped[date] = mapped_column(Date, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscription: Mapped[Subscription] = relationship()
    customer: Mapped[User] = relationship()
    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.id"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice", order_by="Payment.id")

    @property
    def balance(self) -> Decimal:
        return self.total - self.amount_paid


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Money)
    discount_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=0)
    amount: Mapped[Decimal] = mapped_column(Money)  # qty * unit - discount + tax

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    method: Mapped[PaymentMethod] = mapped_column(pg_enum(PaymentMethod, "payment_method"))
    amount: Mapped[Decimal] = mapped_column(Money)
    payment_date: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped[Invoice] = relationship(back_populates="payments")


class Counter(Base):
    """Atomic sequence for human-readable numbers (SUB-0001, INV-0001)."""

    __tablename__ = "counters"

    name: Mapped[str] = mapped_column(String(20), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)
