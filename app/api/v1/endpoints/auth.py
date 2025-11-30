"""
Endpoints de Autenticação para o Tindim Web
"""
from fastapi import APIRouter, HTTPException, Depends, Response, Request
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import secrets
import hashlib
import logging

from app.db.client import supabase

router = APIRouter()
logger = logging.getLogger(__name__)

# --- Schemas ---

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    phone_number: str  # Número do WhatsApp para receber notícias
    name: str
    interests: List[str] = ["economy", "politics"]
    plan: str = "generalista"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    phone_number: Optional[str]
    interests: List[str]
    plan: str
    subscription_status: str
    trial_ends_at: Optional[str]
    created_at: str

class AuthResponse(BaseModel):
    user: UserResponse
    token: str

# --- Helpers ---

def hash_password(password: str) -> str:
    """Hash de senha usando SHA-256 com salt"""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}:{pwd_hash}"

def verify_password(password: str, stored_hash: str) -> bool:
    """Verifica se a senha corresponde ao hash armazenado"""
    try:
        salt, pwd_hash = stored_hash.split(":")
        return hashlib.sha256((password + salt).encode()).hexdigest() == pwd_hash
    except:
        return False

def generate_session_token() -> str:
    """Gera um token de sessão seguro"""
    return secrets.token_urlsafe(32)

def get_token_from_request(request: Request) -> Optional[str]:
    """Extrai o token do header Authorization ou cookie"""
    # Tenta o header Authorization
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]
    
    # Tenta o cookie
    return request.cookies.get("session_token")

async def get_current_user(request: Request) -> dict:
    """Dependency para obter o usuário atual"""
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Busca a sessão
    session_response = supabase.table("sessions")\
        .select("*, users(*)")\
        .eq("token", token)\
        .gt("expires_at", datetime.now(timezone.utc).isoformat())\
        .execute()
    
    if not session_response.data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    session = session_response.data[0]
    user = session.get("users")
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user

# --- Endpoints ---

@router.post("/signup", response_model=AuthResponse)
async def signup(data: SignupRequest, response: Response):
    """Cria uma nova conta de usuário e subscriber para WhatsApp"""
    try:
        # Verifica se email já existe
        existing = supabase.table("users")\
            .select("id")\
            .eq("email", data.email)\
            .execute()
        
        if existing.data:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Verifica se telefone já existe
        existing_phone = supabase.table("subscribers")\
            .select("id")\
            .eq("phone_number", data.phone_number)\
            .execute()
        
        if existing_phone.data:
            raise HTTPException(status_code=400, detail="Phone number already registered")
        
        # Mapeia interesses do frontend para categorias do backend
        interest_mapping = {
            "politics": "POLITICS",
            "economy": "FINANCE",
            "tech": "TECH",
            "business": "BUSINESS",
            "markets": "FINANCE",
            "agro": "AGRO",
            "health": "HEALTH",
            "culture": "ENTERTAINMENT"
        }
        mapped_interests = [interest_mapping.get(i, i.upper()) for i in data.interests]
        
        # 1. Cria o subscriber (para receber WhatsApp)
        subscriber_data = {
            "phone_number": data.phone_number,
            "email": data.email,
            "name": data.name,
            "interests": mapped_interests,
            "plan": data.plan,
            "is_active": True,
            "daily_message_count": 0,
            "daily_ai_count": 0
        }
        
        subscriber_response = supabase.table("subscribers").insert(subscriber_data).execute()
        
        if not subscriber_response.data:
            raise HTTPException(status_code=500, detail="Failed to create subscriber")
        
        subscriber = subscriber_response.data[0]
        
        # 2. Cria o usuário (para login web)
        password_hash = hash_password(data.password)
        trial_ends = datetime.now(timezone.utc) + timedelta(days=5)
        
        user_data = {
            "email": data.email,
            "password_hash": password_hash,
            "name": data.name,
            "phone_number": data.phone_number,
            "interests": mapped_interests,
            "plan": data.plan,
            "subscription_status": "trialing",
            "trial_ends_at": trial_ends.isoformat(),
            "subscriber_id": subscriber["id"]  # Vincula ao subscriber
        }
        
        user_response = supabase.table("users").insert(user_data).execute()
        
        if not user_response.data:
            # Rollback: remove subscriber se falhar criar user
            supabase.table("subscribers").delete().eq("id", subscriber["id"]).execute()
            raise HTTPException(status_code=500, detail="Failed to create user")
        
        user = user_response.data[0]
        
        # 3. Cria sessão
        token = generate_session_token()
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        
        supabase.table("sessions").insert({
            "user_id": user["id"],
            "token": token,
            "expires_at": expires_at.isoformat()
        }).execute()
        
        # Define cookie
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 7  # 7 dias
        )
        
        logger.info(f"Novo usuário criado: {data.email} (WhatsApp: {data.phone_number})")
        
        return AuthResponse(
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                name=user["name"],
                phone_number=user.get("phone_number"),
                interests=user["interests"],
                plan=user["plan"],
                subscription_status=user["subscription_status"],
                trial_ends_at=user.get("trial_ends_at"),
                created_at=user["created_at"]
            ),
            token=token
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no signup: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/login", response_model=AuthResponse)
async def login(data: LoginRequest, response: Response):
    """Faz login do usuário"""
    try:
        # Busca usuário
        user_response = supabase.table("users")\
            .select("*")\
            .eq("email", data.email)\
            .execute()
        
        if not user_response.data:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        user = user_response.data[0]
        
        # Verifica senha
        if not verify_password(data.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Atualiza last_login
        supabase.table("users")\
            .update({"last_login_at": datetime.now(timezone.utc).isoformat()})\
            .eq("id", user["id"])\
            .execute()
        
        # Cria nova sessão
        token = generate_session_token()
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        
        supabase.table("sessions").insert({
            "user_id": user["id"],
            "token": token,
            "expires_at": expires_at.isoformat()
        }).execute()
        
        # Define cookie
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 7
        )
        
        logger.info(f"Login bem-sucedido: {data.email}")
        
        return AuthResponse(
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                name=user["name"],
                phone_number=user.get("phone_number"),
                interests=user["interests"],
                plan=user["plan"],
                subscription_status=user["subscription_status"],
                trial_ends_at=user.get("trial_ends_at"),
                created_at=user["created_at"]
            ),
            token=token
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no login: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/logout")
async def logout(request: Request, response: Response):
    """Faz logout do usuário"""
    token = get_token_from_request(request)
    
    if token:
        # Remove a sessão do banco
        supabase.table("sessions").delete().eq("token", token).execute()
    
    # Remove o cookie
    response.delete_cookie("session_token")
    
    return {"message": "Logged out successfully"}

@router.get("/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    """Retorna os dados do usuário autenticado"""
    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        phone_number=user.get("phone_number"),
        interests=user["interests"],
        plan=user["plan"],
        subscription_status=user["subscription_status"],
        trial_ends_at=user.get("trial_ends_at"),
        created_at=user["created_at"]
    )

@router.put("/me", response_model=UserResponse)
async def update_me(
    interests: Optional[List[str]] = None,
    name: Optional[str] = None,
    phone_number: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Atualiza os dados do usuário"""
    update_data = {}
    
    if interests is not None:
        update_data["interests"] = interests
    if name is not None:
        update_data["name"] = name
    if phone_number is not None:
        update_data["phone_number"] = phone_number
    
    if update_data:
        response = supabase.table("users")\
            .update(update_data)\
            .eq("id", user["id"])\
            .execute()
        
        if response.data:
            user = response.data[0]
    
    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        phone_number=user.get("phone_number"),
        interests=user["interests"],
        plan=user["plan"],
        subscription_status=user["subscription_status"],
        trial_ends_at=user.get("trial_ends_at"),
        created_at=user["created_at"]
    )
