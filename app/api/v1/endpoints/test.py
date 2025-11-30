from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging
from app.services.whatsapp import WhatsAppService
from app.services.audio_generator import AudioGeneratorService
from app.services.chat_assistant import ChatAssistantService
from app.services.ingestion import IngestionService
from app.services.ai_processor import AIProcessor

logger = logging.getLogger(__name__)
router = APIRouter()

class TestMessageRequest(BaseModel):
    phone_number: str
    message: str

class TestAudioRequest(BaseModel):
    subscriber_id: str

@router.post("/send-digest")
async def test_send_digest():
    """Testa o envio de resumos de notícias"""
    try:
        wa = WhatsAppService()
        await wa.broadcast_digest()
        return {"status": "success", "message": "Resumos enviados"}
    except Exception as e:
        logger.error(f"Erro ao enviar resumos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-audio")
async def test_generate_audio(request: TestAudioRequest):
    """Testa a geração de áudio para um assinante"""
    try:
        audio_service = AudioGeneratorService()
        audio_url = await audio_service.generate_personalized_audio(request.subscriber_id)
        return {"status": "success", "audio_url": audio_url}
    except Exception as e:
        logger.error(f"Erro ao gerar áudio: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat-message")
async def test_chat_message(request: TestMessageRequest):
    """Testa o chat assistant"""
    try:
        chat_service = ChatAssistantService()
        response = await chat_service.process_user_message(
            request.phone_number,
            request.message
        )
        return {"status": "success", "response": response}
    except Exception as e:
        logger.error(f"Erro no chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ingest-news")
async def test_ingest_news():
    """Testa a coleta de notícias"""
    try:
        ingestion = IngestionService()
        count = await ingestion.fetch_and_store_news()
        return {"status": "success", "articles_collected": count}
    except Exception as e:
        logger.error(f"Erro na ingestão: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/process-articles")
async def test_process_articles():
    """Testa o processamento de artigos com IA"""
    try:
        ai = AIProcessor()
        count = await ai.process_pending_articles()
        return {"status": "success", "articles_processed": count}
    except Exception as e:
        logger.error(f"Erro no processamento: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check():
    """Verifica se a API está funcionando"""
    return {
        "status": "healthy",
        "service": "Tindim API",
        "version": "1.0.0"
    }
