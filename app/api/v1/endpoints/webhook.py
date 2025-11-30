from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import PlainTextResponse
import logging
from app.config import settings
from app.services.chat_assistant import ChatAssistantService
from app.services.whatsapp import WhatsAppService

logger = logging.getLogger(__name__)
router = APIRouter()

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
async def receive_webhook(request: Request):
    """
    Recebe mensagens do WhatsApp
    Processa mensagens de usuários e responde via chat assistant
    """
    try:
        body = await request.json()
        logger.info(f"Webhook recebido: {body}")
        
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
                    # Extrair dados da mensagem
                    phone_number = message.get("from")
                    message_type = message.get("type")
                    
                    # Processar apenas mensagens de texto
                    if message_type != "text":
                        logger.info(f"Tipo de mensagem não suportado: {message_type}")
                        continue
                    
                    text_content = message.get("text", {}).get("body", "")
                    
                    if not text_content:
                        continue
                    
                    logger.info(f"Mensagem de {phone_number}: {text_content}")
                    
                    # Processar mensagem com o chat assistant
                    chat_service = ChatAssistantService()
                    response_text = await chat_service.process_user_message(
                        phone_number,
                        text_content
                    )
                    
                    # Enviar resposta
                    whatsapp_service = WhatsAppService()
                    await whatsapp_service.send_text_message(phone_number, response_text)
                    
                    logger.info(f"Resposta enviada para {phone_number}")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Erro ao processar webhook: {e}", exc_info=True)
        # Retornar 200 mesmo com erro para não fazer o WhatsApp reenviar
        return {"status": "error", "message": str(e)}
