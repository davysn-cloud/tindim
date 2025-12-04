from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
from datetime import datetime, timedelta
from app.services.ingestion import IngestionService
from app.services.ai_processor import AIProcessor
from app.services.whatsapp import WhatsAppService
from app.services.audio_generator import AudioGeneratorService
from app.db.client import supabase

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


async def run_feedback_jobs():
    """
    Executa jobs de feedback:
    - Verifica usuários inativos (diário)
    - Envia NPS (sexta-feira)
    """
    from app.services.analytics import analytics
    from app.services.feedback import feedback_service
    
    logger.info("--- Iniciando Jobs de Feedback ---")
    
    now = datetime.utcnow()
    
    # 1. Feedback de inatividade (usuários sem atividade há 3+ dias)
    try:
        inactive_users = await analytics.get_inactive_users(days=3, limit=10)
        
        for user in inactive_users:
            try:
                await feedback_service.send_inactivity_check(user["phone_number"])
                logger.info(f"Inactivity check enviado para {user['phone_number']}")
            except Exception as e:
                logger.error(f"Erro ao enviar inactivity check: {e}")
        
        if inactive_users:
            logger.info(f"Enviados {len(inactive_users)} checks de inatividade")
    except Exception as e:
        logger.error(f"Erro no job de inatividade: {e}")
    
    # 2. NPS (apenas sexta-feira)
    if now.weekday() == 4:  # Sexta-feira
        await run_nps_survey()
    
    logger.info("--- Jobs de Feedback Finalizados ---")


async def run_nps_survey():
    """Envia pesquisa NPS para usuários elegíveis"""
    from app.services.analytics import analytics
    from app.services.feedback import feedback_service
    
    logger.info("--- Iniciando NPS Survey ---")
    
    try:
        eligible_users = await analytics.get_nps_eligible_users(days_since_last_nps=30, limit=20)
        
        for user in eligible_users:
            try:
                await feedback_service.send_nps_survey(user["phone_number"])
                logger.info(f"NPS enviado para {user['phone_number']}")
            except Exception as e:
                logger.error(f"Erro ao enviar NPS: {e}")
        
        if eligible_users:
            logger.info(f"Enviados {len(eligible_users)} surveys de NPS")
    except Exception as e:
        logger.error(f"Erro no job de NPS: {e}")
    
    logger.info("--- NPS Survey Finalizado ---")


async def run_daily_reset():
    """Reseta contadores diários de rate limiting"""
    logger.info("--- Resetando contadores diários ---")
    
    try:
        # Tenta usar função SQL
        try:
            supabase.rpc("reset_daily_counters").execute()
        except:
            # Fallback: update direto
            supabase.table("subscribers")\
                .update({
                    "daily_message_count": 0,
                    "daily_ai_count": 0,
                    "last_reset_at": datetime.utcnow().isoformat()
                })\
                .lt("last_reset_at", datetime.utcnow().date().isoformat())\
                .execute()
        
        logger.info("Contadores diários resetados")
    except Exception as e:
        logger.error(f"Erro ao resetar contadores: {e}")


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
    
    # Jobs de feedback às 18:00 (horário de Brasília = 21:00 UTC)
    # - Verifica usuários inativos (diário)
    # - Envia NPS (sexta-feira)
    scheduler.add_job(run_feedback_jobs, CronTrigger(hour=21, minute=0))
    
    # Reset de contadores diários à meia-noite UTC
    scheduler.add_job(run_daily_reset, CronTrigger(hour=0, minute=5))
    
    scheduler.start()
    logger.info("Scheduler iniciado (Resumos: 07:00/18:00 | Áudio: 08:00 | Feedback: 18:00 | Ingestão: 2h)")


# Funções auxiliares para execução manual
async def trigger_nps_manually():
    """Dispara NPS manualmente (para testes)"""
    await run_nps_survey()

async def trigger_inactivity_check_manually():
    """Dispara check de inatividade manualmente (para testes)"""
    await run_feedback_jobs()
