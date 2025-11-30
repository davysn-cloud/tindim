from fastapi import APIRouter
from app.api.v1.endpoints import subscription, webhook, test

api_router = APIRouter()
api_router.include_router(subscription.router, tags=["subscription"])
api_router.include_router(webhook.router, prefix="/webhook", tags=["webhook"])
api_router.include_router(test.router, prefix="/test", tags=["test"])
