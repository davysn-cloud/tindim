from fastapi import APIRouter
from app.api.v1.endpoints import subscription, webhook, test, auth, stripe

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(stripe.router, prefix="/stripe", tags=["stripe"])
api_router.include_router(subscription.router, tags=["subscription"])
api_router.include_router(webhook.router, prefix="/webhook", tags=["webhook"])
api_router.include_router(test.router, prefix="/test", tags=["test"])
