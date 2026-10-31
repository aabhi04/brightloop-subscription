from fastapi import APIRouter

from app.api import auth, users

api_router = APIRouter(prefix="/api")
for module in (auth, users):
    api_router.include_router(module.router)
