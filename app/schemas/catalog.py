from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.schemas import ORMModel
from app.utils.constants import BillingPeriod, DiscountScope, DiscountType, PlanStatus, TaxType

NonNegMoney = Field(ge=0, max_digits=12, decimal_places=2)


# ---------- Products ----------
class VariantIn(BaseModel):
    attribute: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=80)
    extra_price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)


class VariantOut(ORMModel):
    id: int
    product_id: int
    attribute: str
    value: str
    extra_price: Decimal


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    type: str = Field(default="SERVICE", max_length=40)
    sales_price: Decimal = NonNegMoney
    cost_price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    notes: str | None = None
    variants: list[VariantIn] = []  # only used on create


class ProductOut(ORMModel):
    id: int
    name: str
    type: str
    sales_price: Decimal
    cost_price: Decimal
    notes: str | None
    variants: list[VariantOut] = []


# ---------- Plans ----------
class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    billing_period: BillingPeriod
    min_quantity: int = Field(default=1, ge=1)
    start_date: date
    end_date: date | None = None
    auto_close: bool = False
    closable: bool = True
    pausable: bool = True
    renewable: bool = True

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class PlanOut(ORMModel):
    id: int
    name: str
    price: Decimal
    billing_period: BillingPeriod
    min_quantity: int
    start_date: date
    end_date: date | None
    auto_close: bool
    closable: bool
    pausable: bool
    renewable: bool
    status: PlanStatus


# ---------- Taxes ----------
class TaxIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: TaxType
    rate: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    is_active: bool = True

    @model_validator(mode="after")
    def check_rate(self):
        if self.type == TaxType.PERCENT and self.rate > 100:
            raise ValueError("Percentage tax rate cannot exceed 100")
        return self


class TaxOut(ORMModel):
    id: int
    name: str
    type: TaxType
    rate: Decimal
    is_active: bool


# ---------- Discounts ----------
class DiscountIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: DiscountType
    value: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    min_purchase: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    min_quantity: int = Field(default=0, ge=0)
    start_date: date
    end_date: date
    usage_limit: int = Field(ge=1)
    applies_to: DiscountScope
    product_ids: list[int] = []

    @model_validator(mode="after")
    def check(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.type == DiscountType.PERCENT and self.value > 100:
            raise ValueError("Percentage discount cannot exceed 100")
        if self.applies_to == DiscountScope.PRODUCT and not self.product_ids:
            raise ValueError("Product discounts need at least one product")
        return self


class ProductRef(ORMModel):
    id: int
    name: str


class DiscountOut(ORMModel):
    id: int
    name: str
    type: DiscountType
    value: Decimal
    min_purchase: Decimal
    min_quantity: int
    start_date: date
    end_date: date
    usage_limit: int
    used_count: int
    applies_to: DiscountScope
    products: list[ProductRef] = []


# ---------- Quotation templates ----------
class TemplateLineIn(BaseModel):
    product_id: int
    variant_id: int | None = None
    quantity: int = Field(default=1, ge=1)


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    validity_days: int = Field(ge=1)
    plan_id: int
    lines: list[TemplateLineIn] = Field(min_length=1)


class TemplateLineOut(ORMModel):
    id: int
    product_id: int
    variant_id: int | None
    quantity: int
    product: ProductRef
    variant: VariantOut | None


class TemplateOut(ORMModel):
    id: int
    name: str
    validity_days: int
    plan_id: int
    plan: PlanOut
    lines: list[TemplateLineOut]
