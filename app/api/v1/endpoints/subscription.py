from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from app.db.client import supabase
import logging
import re

router = APIRouter()

logger = logging.getLogger(__name__)

class SubscriberCreate(BaseModel):
    name: str
    phone: str
    email: EmailStr
    interests: list[str] = ["GERAL"]

def format_phone(phone: str) -> str:
    # Remove tudo que não é número
    nums = re.sub(r'\D', '', phone)
    # Adiciona código do país se faltar (Assumindo BR 55 por padrão para MVP)
    if len(nums) <= 11 and not nums.startswith('55'):
        nums = '55' + nums
    return nums

@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe_user(sub: SubscriberCreate):
    try:
        # Formata telefone para padrão WhatsApp (apenas números)
        clean_phone = format_phone(sub.phone)
        
        # Verifica se já existe (por email ou telefone)
        existing = supabase.table("subscribers").select("*").or_(f"email.eq.{sub.email},phone_number.eq.{clean_phone}").execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="Usuário já cadastrado com este email ou telefone.")

        data = {
            "name": sub.name,
            "email": sub.email,
            "phone_number": clean_phone,
            "interests": sub.interests,
            "is_active": True
        }
        
        result = supabase.table("subscribers").insert(data).execute()
        return {"message": "Inscrição realizada com sucesso!", "id": result.data[0]['id']}

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Erro ao inscrever usuário: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao processar inscrição.")
