"""
Serviço de Analytics e Tracking de Eventos
Rastreia comportamento do usuário para insights e melhorias
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from app.db.client import supabase

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Serviço de tracking de eventos e analytics"""
    
    # Tipos de eventos suportados
    EVENT_TYPES = [
        "message_sent",      # Usuário enviou mensagem
        "message_received",  # Usuário recebeu mensagem
        "button_clicked",    # Clicou em botão interativo
        "list_selected",     # Selecionou item de lista
        "onboarding_step",   # Avançou no onboarding
        "digest_opened",     # Abriu/leu resumo
        "audio_played",      # Ouviu áudio
        "feedback_given",    # Deu feedback
        "bug_reported",      # Reportou bug
        "config_changed",    # Alterou configurações
        "subscription_changed",  # Mudou plano
        "deep_dive_used",    # Usou deep dive
    ]
    
    async def track_event(
        self, 
        subscriber_id: str, 
        event_type: str, 
        event_data: Dict = None,
        session_id: str = None
    ) -> bool:
        """
        Registra um evento do usuário.
        
        Args:
            subscriber_id: ID do subscriber
            event_type: Tipo do evento (ver EVENT_TYPES)
            event_data: Dados adicionais do evento
            session_id: ID da sessão (opcional)
        
        Returns:
            True se registrado com sucesso
        """
        try:
            supabase.table("user_events").insert({
                "subscriber_id": subscriber_id,
                "event_type": event_type,
                "event_data": event_data or {},
                "session_id": session_id,
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            
            logger.debug(f"Event tracked: {event_type} for {subscriber_id[:8]}...")
            return True
            
        except Exception as e:
            # Não falha silenciosamente, mas não bloqueia o fluxo principal
            logger.warning(f"Failed to track event {event_type}: {e}")
            return False
    
    async def track_message(
        self, 
        subscriber_id: str, 
        direction: str,  # "sent" ou "received"
        message_type: str = "text",
        content_preview: str = None
    ) -> bool:
        """Atalho para tracking de mensagens"""
        event_type = f"message_{direction}"
        return await self.track_event(
            subscriber_id,
            event_type,
            {
                "message_type": message_type,
                "content_preview": content_preview[:50] if content_preview else None
            }
        )
    
    async def track_button_click(
        self, 
        subscriber_id: str, 
        button_id: str,
        context: str = None
    ) -> bool:
        """Atalho para tracking de cliques em botões"""
        return await self.track_event(
            subscriber_id,
            "button_clicked",
            {"button_id": button_id, "context": context}
        )
    
    async def track_onboarding_step(
        self, 
        subscriber_id: str, 
        step: str,
        data: Dict = None
    ) -> bool:
        """Atalho para tracking de passos do onboarding"""
        return await self.track_event(
            subscriber_id,
            "onboarding_step",
            {"step": step, **(data or {})}
        )
    
    async def get_user_activity(self, subscriber_id: str, days: int = 7) -> Dict:
        """
        Retorna métricas de atividade do usuário.
        
        Returns:
            Dict com métricas de atividade
        """
        since = datetime.utcnow() - timedelta(days=days)
        
        try:
            response = supabase.table("user_events")\
                .select("event_type, created_at")\
                .eq("subscriber_id", subscriber_id)\
                .gte("created_at", since.isoformat())\
                .order("created_at", desc=True)\
                .execute()
            
            events = response.data or []
            
            # Agrupa por tipo
            by_type = {}
            for e in events:
                t = e["event_type"]
                by_type[t] = by_type.get(t, 0) + 1
            
            return {
                "total_events": len(events),
                "events_by_type": by_type,
                "messages_sent": by_type.get("message_sent", 0),
                "buttons_clicked": by_type.get("button_clicked", 0),
                "last_activity": events[0]["created_at"] if events else None,
                "days_since_last_activity": self._days_since_last_activity(events),
                "is_active": len(events) > 0
            }
            
        except Exception as e:
            logger.error(f"Error getting user activity: {e}")
            return {"total_events": 0, "is_active": False}
    
    async def get_inactive_users(self, days: int = 3, limit: int = 50) -> List[Dict]:
        """
        Retorna usuários inativos há X dias.
        Usado para enviar feedback de inatividade.
        """
        threshold = datetime.utcnow() - timedelta(days=days)
        
        try:
            response = supabase.table("subscribers")\
                .select("id, phone_number, name, last_message_at")\
                .eq("is_active", True)\
                .lt("last_message_at", threshold.isoformat())\
                .is_("last_feedback_at", "null")\
                .limit(limit)\
                .execute()
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"Error getting inactive users: {e}")
            return []
    
    async def get_nps_eligible_users(self, days_since_last_nps: int = 30, limit: int = 20) -> List[Dict]:
        """
        Retorna usuários elegíveis para NPS.
        Critérios: ativos, não receberam NPS há X dias.
        """
        threshold = datetime.utcnow() - timedelta(days=days_since_last_nps)
        
        try:
            # Usuários que nunca receberam NPS ou receberam há mais de X dias
            response = supabase.table("subscribers")\
                .select("id, phone_number, name")\
                .eq("is_active", True)\
                .or_(f"last_nps_at.is.null,last_nps_at.lt.{threshold.isoformat()}")\
                .limit(limit)\
                .execute()
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"Error getting NPS eligible users: {e}")
            return []
    
    async def get_engagement_summary(self) -> Dict:
        """Retorna resumo de engajamento geral"""
        try:
            # Total de usuários ativos
            active_response = supabase.table("subscribers")\
                .select("id", count="exact")\
                .eq("is_active", True)\
                .execute()
            
            # Eventos últimos 7 dias
            week_ago = datetime.utcnow() - timedelta(days=7)
            events_response = supabase.table("user_events")\
                .select("id", count="exact")\
                .gte("created_at", week_ago.isoformat())\
                .execute()
            
            # Beta testers
            beta_response = supabase.table("subscribers")\
                .select("id", count="exact")\
                .eq("is_beta_tester", True)\
                .execute()
            
            return {
                "total_active_users": active_response.count or 0,
                "events_last_7_days": events_response.count or 0,
                "total_beta_testers": beta_response.count or 0,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting engagement summary: {e}")
            return {}
    
    def _days_since_last_activity(self, events: List) -> int:
        """Calcula dias desde última atividade"""
        if not events:
            return 999
        
        try:
            last = events[0]["created_at"]
            last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            now = datetime.utcnow().replace(tzinfo=last_dt.tzinfo)
            return (now - last_dt).days
        except:
            return 999


# Instância global
analytics = AnalyticsService()
