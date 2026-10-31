from fastapi import APIRouter

from app.api import auth, discounts, plans, products, quotation_templates, subscriptions, taxes, users

api_router = APIRouter(prefix="/api")
for module in (auth, users, products, plans, taxes, discounts, quotation_templates, subscriptions):
    api_router.include_router(module.router)
