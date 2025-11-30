from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
from app.services.ingestion import IngestionService
from app.services.ai_processor import AIProcessor
from app.services.whatsapp import WhatsAppService
from app.services.audio_generator import AudioGeneratorService

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

async def run_daily_cycle():
    """Ciclo principal: coleta, processa e envia resumos de texto"""
    logger.info("--- Iniciando Ciclo Agendado ---")
    
    # 1. Ingestão
    ingestion = IngestionService()
    await ingestion.fetch_and_store_news()
    
    # 2. Processamento IA
    ai = AIProcessor()
    await ai.process_pending_articles()
    
    # 3. Envio de resumos de texto
    wa = WhatsAppService()
    await wa.broadcast_digest()
    
    logger.info("--- Ciclo Agendado Finalizado ---")

async def run_audio_broadcast():
    """Gera e envia áudios personalizados"""
    logger.info("--- Iniciando Broadcast de Áudio ---")
    
    audio_service = AudioGeneratorService()
    await audio_service.broadcast_audio_digests()
    
    logger.info("--- Broadcast de Áudio Finalizado ---")

def start_scheduler():
    # Resumos de texto às 07:00 e 18:00
    scheduler.add_job(run_daily_cycle, CronTrigger(hour=7, minute=0))
    scheduler.add_job(run_daily_cycle, CronTrigger(hour=18, minute=0))
    
    # Áudios personalizados às 08:00 (após o processamento da manhã)
    scheduler.add_job(run_audio_broadcast, CronTrigger(hour=8, minute=0))
    
    # Ingestão contínua a cada 2 horas para manter DB atualizado
    scheduler.add_job(
        lambda: IngestionService().fetch_and_store_news(),
        CronTrigger(hour="*/2")
    )
    
    scheduler.start()
    logger.info("Scheduler iniciado (Resumos: 07:00 e 18:00 | Áudio: 08:00 | Ingestão: a cada 2h)")
