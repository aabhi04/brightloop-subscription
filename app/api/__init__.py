from fastapi import APIRouter

from app.api import (
    auth,
    discounts,
    invoices,
    payments,
    plans,
    portal,
    products,
    quotation_templates,
    subscriptions,
    taxes,
    users,
)

api_router = APIRouter(prefix="/api")
for module in (
    auth,
    users,
    products,
    plans,
    taxes,
    discounts,
    quotation_templates,
    subscriptions,
    invoices,
    payments,
    portal,
):
    api_router.include_router(module.router)
