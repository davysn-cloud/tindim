"""
Endpoints de Pagamento com Stripe para o Tindim
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Header
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import logging
import stripe
import os

from app.db.client import supabase
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

# Configuração do Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5000")

# Preços dos planos (criar no Stripe Dashboard)
PRICE_IDS = {
    "generalista": os.getenv("STRIPE_PRICE_GENERALISTA", "price_generalista"),
    "estrategista": os.getenv("STRIPE_PRICE_ESTRATEGISTA", "price_estrategista")
}

# --- Schemas ---

class CreateCheckoutRequest(BaseModel):
    plan: str  # "generalista" ou "estrategista"

class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str

class PortalResponse(BaseModel):
    portal_url: str

# --- Endpoints ---

@router.post("/create-checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    data: CreateCheckoutRequest,
    user: dict = Depends(get_current_user)
):
    """Cria uma sessão de checkout do Stripe"""
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    
    if data.plan not in PRICE_IDS:
        raise HTTPException(status_code=400, detail="Invalid plan")
    
    try:
        # Verifica se já tem customer_id
        customer_id = user.get("stripe_customer_id")
        
        if not customer_id:
            # Cria customer no Stripe
            customer = stripe.Customer.create(
                email=user["email"],
                name=user["name"],
                metadata={"user_id": user["id"]}
            )
            customer_id = customer.id
            
            # Salva no banco
            supabase.table("users")\
                .update({"stripe_customer_id": customer_id})\
                .eq("id", user["id"])\
                .execute()
        
        # Cria checkout session
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{
                "price": PRICE_IDS[data.plan],
                "quantity": 1
            }],
            mode="subscription",
            success_url=f"{FRONTEND_URL}/?checkout=success",
            cancel_url=f"{FRONTEND_URL}/?checkout=canceled",
            subscription_data={
                "trial_period_days": 5,
                "metadata": {
                    "user_id": user["id"],
                    "plan": data.plan
                }
            },
            metadata={
                "user_id": user["id"],
                "plan": data.plan
            }
        )
        
        logger.info(f"Checkout criado para {user['email']}: {session.id}")
        
        return CheckoutResponse(
            checkout_url=session.url,
            session_id=session.id
        )
        
    except stripe.error.StripeError as e:
        logger.error(f"Erro Stripe: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao criar checkout: {e}")
        raise HTTPException(status_code=500, detail="Failed to create checkout")

@router.post("/create-portal", response_model=PortalResponse)
async def create_customer_portal(user: dict = Depends(get_current_user)):
    """Cria uma sessão do Customer Portal do Stripe"""
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    
    customer_id = user.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="No subscription found")
    
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{FRONTEND_URL}/"
        )
        
        return PortalResponse(portal_url=session.url)
        
    except stripe.error.StripeError as e:
        logger.error(f"Erro Stripe Portal: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature")
):
    """Webhook para receber eventos do Stripe"""
    if not STRIPE_WEBHOOK_SECRET:
        logger.warning("Stripe webhook secret not configured")
        return {"received": True}
    
    payload = await request.body()
    
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    event_type = event["type"]
    data = event["data"]["object"]
    
    logger.info(f"Stripe webhook: {event_type}")
    
    # Processa eventos
    if event_type == "checkout.session.completed":
        await handle_checkout_completed(data)
    
    elif event_type == "customer.subscription.created":
        await handle_subscription_created(data)
    
    elif event_type == "customer.subscription.updated":
        await handle_subscription_updated(data)
    
    elif event_type == "customer.subscription.deleted":
        await handle_subscription_deleted(data)
    
    elif event_type == "invoice.payment_succeeded":
        await handle_payment_succeeded(data)
    
    elif event_type == "invoice.payment_failed":
        await handle_payment_failed(data)
    
    return {"received": True}

# --- Event Handlers ---

async def handle_checkout_completed(session: dict):
    """Processa checkout completado"""
    user_id = session.get("metadata", {}).get("user_id")
    subscription_id = session.get("subscription")
    customer_id = session.get("customer")
    
    if user_id and subscription_id:
        supabase.table("users")\
            .update({
                "stripe_subscription_id": subscription_id,
                "stripe_customer_id": customer_id,
                "subscription_status": "trialing"
            })\
            .eq("id", user_id)\
            .execute()
        
        logger.info(f"Checkout completado para user {user_id}")

async def handle_subscription_created(subscription: dict):
    """Processa nova assinatura"""
    customer_id = subscription.get("customer")
    status = subscription.get("status")
    
    # Busca usuário pelo customer_id
    user_response = supabase.table("users")\
        .select("id")\
        .eq("stripe_customer_id", customer_id)\
        .execute()
    
    if user_response.data:
        user_id = user_response.data[0]["id"]
        supabase.table("users")\
            .update({
                "stripe_subscription_id": subscription["id"],
                "subscription_status": status
            })\
            .eq("id", user_id)\
            .execute()
        
        logger.info(f"Assinatura criada para user {user_id}: {status}")

async def handle_subscription_updated(subscription: dict):
    """Processa atualização de assinatura"""
    customer_id = subscription.get("customer")
    status = subscription.get("status")
    plan = subscription.get("metadata", {}).get("plan")
    
    update_data = {"subscription_status": status}
    if plan:
        update_data["plan"] = plan
    
    supabase.table("users")\
        .update(update_data)\
        .eq("stripe_customer_id", customer_id)\
        .execute()
    
    logger.info(f"Assinatura atualizada para customer {customer_id}: {status}")

async def handle_subscription_deleted(subscription: dict):
    """Processa cancelamento de assinatura"""
    customer_id = subscription.get("customer")
    
    supabase.table("users")\
        .update({
            "subscription_status": "canceled",
            "stripe_subscription_id": None
        })\
        .eq("stripe_customer_id", customer_id)\
        .execute()
    
    logger.info(f"Assinatura cancelada para customer {customer_id}")

async def handle_payment_succeeded(invoice: dict):
    """Processa pagamento bem-sucedido"""
    customer_id = invoice.get("customer")
    
    supabase.table("users")\
        .update({"subscription_status": "active"})\
        .eq("stripe_customer_id", customer_id)\
        .execute()
    
    logger.info(f"Pagamento recebido de customer {customer_id}")

async def handle_payment_failed(invoice: dict):
    """Processa falha de pagamento"""
    customer_id = invoice.get("customer")
    
    supabase.table("users")\
        .update({"subscription_status": "past_due"})\
        .eq("stripe_customer_id", customer_id)\
        .execute()
    
    logger.info(f"Pagamento falhou para customer {customer_id}")
