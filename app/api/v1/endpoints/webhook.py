from fastapi import APIRouter, Request, Response, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Set
from app.config import settings
from app.services.whatsapp_onboarding import whatsapp_onboarding

logger = logging.getLogger(__name__)
router = APIRouter()

# Cache de mensagens processadas para evitar duplicação
# Formato: {message_id: timestamp}
_processed_messages: dict = {}
_processing_lock = asyncio.Lock()

# Limpa mensagens antigas a cada 5 minutos
async def _cleanup_old_messages():
    """Remove mensagens processadas há mais de 5 minutos"""
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    to_remove = [mid for mid, ts in _processed_messages.items() if ts < cutoff]
    for mid in to_remove:
        _processed_messages.pop(mid, None)

@router.get("/whatsapp")
async def verify_webhook(request: Request):
    """
    Webhook de verificação do WhatsApp
    O WhatsApp envia uma requisição GET para verificar o webhook
    """
    # Parâmetros enviados pelo WhatsApp
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    logger.info(f"Verificação de webhook: mode={mode}, token={token}")
    
    # Verificar token
    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verificado com sucesso!")
        return PlainTextResponse(content=challenge, status_code=200)
    else:
        logger.warning("Falha na verificação do webhook")
        raise HTTPException(status_code=403, detail="Forbidden")

@router.post("/whatsapp")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Recebe mensagens do WhatsApp
    Processa mensagens de usuários e responde via chat assistant
    """
    try:
        body = await request.json()
        logger.info(f"Webhook recebido: {body}")
        
        # Limpa mensagens antigas em background
        background_tasks.add_task(_cleanup_old_messages)
        
        # Verificar se é uma mensagem
        if "entry" not in body:
            return {"status": "ok"}
        
        for entry in body["entry"]:
            if "changes" not in entry:
                continue
                
            for change in entry["changes"]:
                if change.get("field") != "messages":
                    continue
                
                value = change.get("value", {})
                
                # Verificar se há mensagens
                if "messages" not in value:
                    continue
                
                for message in value["messages"]:
                    # === DEDUPLICAÇÃO: Verifica se já processamos esta mensagem ===
                    message_id = message.get("id")
                    if message_id:
                        async with _processing_lock:
                            if message_id in _processed_messages:
                                logger.info(f"Mensagem {message_id} já processada, ignorando duplicata")
                                continue
                            # Marca como processada ANTES de processar
                            _processed_messages[message_id] = datetime.utcnow()
                    
                    # Extrair dados da mensagem
                    phone_number = message.get("from")
                    message_type = message.get("type")
                    
                    # Extrair conteúdo baseado no tipo
                    text_content = ""
                    
                    if message_type == "text":
                        text_content = message.get("text", {}).get("body", "")
                    
                    elif message_type == "interactive":
                        # Resposta de botão interativo
                        interactive = message.get("interactive", {})
                        interactive_type = interactive.get("type")
                        
                        if interactive_type == "button_reply":
                            # Clique em botão
                            text_content = interactive.get("button_reply", {}).get("id", "")
                        elif interactive_type == "list_reply":
                            # Seleção de lista
                            text_content = interactive.get("list_reply", {}).get("id", "")
                        
                        logger.info(f"Resposta interativa: {text_content}")
                    
                    else:
                        logger.info(f"Tipo de mensagem não suportado: {message_type}")
                        # Para outros tipos, ignora
                        continue
                    
                    if not text_content:
                        continue
                    
                    logger.info(f"Mensagem de {phone_number}: {text_content} (tipo: {message_type})")
                    
                    # Processar mensagem com o sistema de onboarding
                    # Executa em background para responder rápido ao WhatsApp
                    background_tasks.add_task(
                        whatsapp_onboarding.process_message,
                        phone_number,
                        text_content,
                        message_type
                    )
                    
                    logger.info(f"Mensagem enfileirada para processamento: {phone_number}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Erro ao processar webhook: {e}", exc_info=True)
        # Retornar 200 mesmo com erro para não fazer o WhatsApp reenviar
        return {"status": "error", "message": str(e)}
