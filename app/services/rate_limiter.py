"""
Serviço de Rate Limiting
Controla limites de uso por plano e previne abuso
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple
from app.db.client import supabase

logger = logging.getLogger(__name__)


class RateLimiter:
    """Controle de rate limiting por usuário"""
    
    # Limites por plano (por dia)
    LIMITS = {
        "generalista": {
            "messages_per_day": 100,
            "ai_interactions_per_day": 10,
            "config_changes_per_day": 5
        },
        "estrategista": {
            "messages_per_day": 300,
            "ai_interactions_per_day": 30,
            "config_changes_per_day": 10
        },
        "beta_tester": {
            "messages_per_day": 500,
            "ai_interactions_per_day": 50,
            "config_changes_per_day": 20
        }
    }
    
    async def check_limit(
        self, 
        subscriber_id: str, 
        action: str = "message"
    ) -> Tuple[bool, str]:
        """
        Verifica se usuário pode realizar ação.
        
        Args:
            subscriber_id: ID do subscriber
            action: Tipo de ação ('message', 'ai', 'config')
        
        Returns:
            (allowed, message)
            - allowed: True se pode realizar a ação
            - message: Mensagem de erro se não permitido
        """
        try:
            # Busca subscriber
            response = supabase.table("subscribers")\
                .select("plan, is_beta_tester, daily_message_count, daily_ai_count, last_reset_at")\
                .eq("id", subscriber_id)\
                .execute()
            
            if not response.data:
                return False, "Usuário não encontrado"
            
            sub = response.data[0]
            
            # Verifica se precisa resetar contadores (novo dia)
            await self._check_daily_reset(subscriber_id, sub)
            
            # Determina plano efetivo
            plan = "beta_tester" if sub.get("is_beta_tester") else sub.get("plan", "generalista")
            limits = self.LIMITS.get(plan, self.LIMITS["generalista"])
            
            # Verifica limite baseado na ação
            if action == "message":
                current = sub.get("daily_message_count", 0)
                limit = limits["messages_per_day"]
                
                if current >= limit:
                    return False, self._get_limit_message("mensagens", limit, plan)
            
            elif action == "ai":
                current = sub.get("daily_ai_count", 0)
                limit = limits["ai_interactions_per_day"]
                
                if current >= limit:
                    return False, self._get_ai_limit_message(limit, plan)
            
            return True, ""
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            # Em caso de erro, permite a ação (fail open)
            return True, ""
    
    async def increment_counter(
        self, 
        subscriber_id: str, 
        action: str = "message"
    ) -> bool:
        """
        Incrementa contador de uso.
        Usa função SQL para incremento atômico.
        """
        try:
            field = "daily_message_count" if action == "message" else "daily_ai_count"
            
            # Tenta usar RPC para incremento atômico
            try:
                supabase.rpc("increment_counter", {
                    "p_subscriber_id": subscriber_id,
                    "p_counter_field": field
                }).execute()
            except:
                # Fallback: update direto (menos seguro, mas funciona)
                current = supabase.table("subscribers")\
                    .select(field)\
                    .eq("id", subscriber_id)\
                    .execute()
                
                if current.data:
                    new_value = (current.data[0].get(field) or 0) + 1
                    supabase.table("subscribers")\
                        .update({
                            field: new_value,
                            "last_message_at": datetime.utcnow().isoformat()
                        })\
                        .eq("id", subscriber_id)\
                        .execute()
            
            return True
            
        except Exception as e:
            logger.error(f"Error incrementing counter: {e}")
            return False
    
    async def get_usage_stats(self, subscriber_id: str) -> Dict:
        """Retorna estatísticas de uso do usuário"""
        try:
            response = supabase.table("subscribers")\
                .select("plan, is_beta_tester, daily_message_count, daily_ai_count, last_reset_at")\
                .eq("id", subscriber_id)\
                .execute()
            
            if not response.data:
                return {}
            
            sub = response.data[0]
            plan = "beta_tester" if sub.get("is_beta_tester") else sub.get("plan", "generalista")
            limits = self.LIMITS.get(plan, self.LIMITS["generalista"])
            
            return {
                "plan": plan,
                "messages": {
                    "used": sub.get("daily_message_count", 0),
                    "limit": limits["messages_per_day"],
                    "remaining": limits["messages_per_day"] - sub.get("daily_message_count", 0)
                },
                "ai_interactions": {
                    "used": sub.get("daily_ai_count", 0),
                    "limit": limits["ai_interactions_per_day"],
                    "remaining": limits["ai_interactions_per_day"] - sub.get("daily_ai_count", 0)
                },
                "resets_at": self._get_next_reset_time()
            }
            
        except Exception as e:
            logger.error(f"Error getting usage stats: {e}")
            return {}
    
    async def _check_daily_reset(self, subscriber_id: str, sub: Dict) -> None:
        """Reseta contadores se passou da meia-noite"""
        last_reset = sub.get("last_reset_at")
        
        if not last_reset:
            return
        
        try:
            last_reset_dt = datetime.fromisoformat(last_reset.replace("Z", "+00:00"))
            now = datetime.utcnow().replace(tzinfo=last_reset_dt.tzinfo)
            
            # Se o último reset foi em um dia anterior, reseta
            if last_reset_dt.date() < now.date():
                supabase.table("subscribers")\
                    .update({
                        "daily_message_count": 0,
                        "daily_ai_count": 0,
                        "last_reset_at": now.isoformat()
                    })\
                    .eq("id", subscriber_id)\
                    .execute()
                
                logger.debug(f"Daily counters reset for {subscriber_id[:8]}...")
                
        except Exception as e:
            logger.error(f"Error checking daily reset: {e}")
    
    def _get_limit_message(self, resource: str, limit: int, plan: str) -> str:
        """Gera mensagem de limite atingido"""
        base_msg = f"Você atingiu o limite diário de {limit} {resource}. 😊"
        
        if plan == "generalista":
            return (
                f"{base_msg}\n\n"
                "💡 *Dica:* Faça upgrade para o plano *Estrategista* "
                "e tenha 3x mais limite!\n\n"
                "Volte amanhã para mais conversas!"
            )
        
        return f"{base_msg}\n\nVolte amanhã para mais!"
    
    def _get_ai_limit_message(self, limit: int, plan: str) -> str:
        """Gera mensagem de limite de IA atingido"""
        if plan == "generalista":
            return (
                f"Você atingiu o limite de {limit} interações com IA por hoje. 😊\n\n"
                "💡 *Dica:* Upgrade pro *Estrategista* = 30 interações/dia!\n\n"
                "Volte amanhã para mais conversas!"
            )
        
        return (
            f"Você atingiu o limite de {limit} interações com IA por hoje.\n\n"
            "Volte amanhã para mais conversas! 😊"
        )
    
    def _get_next_reset_time(self) -> str:
        """Retorna horário do próximo reset (meia-noite UTC)"""
        now = datetime.utcnow()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return tomorrow.isoformat()


# Instância global
rate_limiter = RateLimiter()
