from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.schemas import ORMModel
from app.schemas.catalog import PlanOut, ProductRef, TaxOut, VariantOut
from app.utils.constants import SubscriptionStatus


class SubscriptionLineIn(BaseModel):
    product_id: int
    variant_id: int | None = None
    quantity: int = Field(default=1, ge=1)
    tax_id: int | None = None


class SubscriptionIn(BaseModel):
    customer_id: int
    plan_id: int
    start_date: date
    expiry_date: date | None = None
    payment_terms: int = Field(default=15, ge=0, le=365)
    lines: list[SubscriptionLineIn] = []

    @model_validator(mode="after")
    def check_dates(self):
        if self.expiry_date and self.expiry_date < self.start_date:
            raise ValueError("expiry_date must be on or after start_date")
        return self


class FromTemplateIn(BaseModel):
    customer_id: int
    start_date: date | None = None
    payment_terms: int = Field(default=15, ge=0, le=365)


class StatusIn(BaseModel):
    status: SubscriptionStatus


class CustomerRef(ORMModel):
    id: int
    name: str
    email: str


class SubscriptionLineOut(ORMModel):
    id: int
    product_id: int
    variant_id: int | None
    quantity: int
    unit_price: Decimal
    tax_id: int | None
    amount: Decimal
    product: ProductRef
    variant: VariantOut | None
    tax: TaxOut | None


class SubscriptionSummaryOut(ORMModel):
    id: int
    number: str
    customer: CustomerRef
    plan: PlanOut
    start_date: date
    expiry_date: date | None
    payment_terms: int
    status: SubscriptionStatus
    next_billing_date: date | None


class SubscriptionOut(SubscriptionSummaryOut):
    lines: list[SubscriptionLineOut]
