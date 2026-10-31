from fastapi import APIRouter

from app.web import admin, auth, portal, staff

web_router = APIRouter(include_in_schema=False)
for module in (auth, admin, staff, portal):
    web_router.include_router(module.router)
