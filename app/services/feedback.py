"""
Serviço de Coleta e Processamento de Feedback
Gerencia NPS, feedback implícito, bug reports e sugestões
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from app.db.client import supabase

logger = logging.getLogger(__name__)


class FeedbackService:
    """Gerencia coleta de feedback dos usuários"""
    
    # Configurações
    INACTIVITY_DAYS = 3  # Dias sem atividade para pedir feedback
    NPS_INTERVAL_DAYS = 30  # Intervalo mínimo entre NPS
    
    # Respostas para feedback implícito
    IMPLICIT_RESPONSES = {
        1: "Entendi! Vou maneirar nas mensagens. 🕐\n\nVocê pode ajustar os horários digitando *configurações*.",
        2: "Hmm, conteúdo chato né? 📰\n\nBora ajustar seus tópicos! Digite *configurações* pra escolher outros temas.",
        3: "Que bom que tá tudo certo! 😊\n\nQuando quiser, é só chamar. Tô sempre por aqui!"
    }
    
    # Respostas para NPS
    NPS_RESPONSES = {
        "promoter": "🎉 Que massa! Obrigado pela confiança!\n\nSe quiser indicar, é só mandar o link: tfraga.com/tindim",
        "passive": "😊 Valeu pelo feedback!\n\nMe conta: o que posso fazer pra virar um 10?",
        "detractor": "😔 Entendi... Obrigado pela honestidade.\n\nMe conta mais? Quero muito melhorar pra você!"
    }
    
    async def send_inactivity_check(self, phone_number: str) -> bool:
        """
        Envia pergunta de feedback para usuário inativo.
        Chamado pelo scheduler após X dias sem atividade.
        """
        from app.services.whatsapp_onboarding import WhatsAppOnboarding
        
        try:
            onboarding = WhatsAppOnboarding()
            
            message = (
                "👋 Oi! Percebi que você sumiu...\n\n"
                "Falei demais? Ou as notícias estavam chatas? 🤔\n\n"
                "Me ajuda a melhorar:\n"
                "• Digite *1* para 'Muitas mensagens'\n"
                "• Digite *2* para 'Conteúdo irrelevante'\n"
                "• Digite *3* para 'Tudo certo, só ocupado'\n\n"
                "_Sua opinião vale ouro pra mim!_ ✨"
            )
            
            await onboarding._send_text_message(phone_number, message)
            
            # Marca que pedimos feedback
            supabase.table("subscribers")\
                .update({"last_feedback_at": datetime.utcnow().isoformat()})\
                .eq("phone_number", phone_number)\
                .execute()
            
            logger.info(f"Inactivity check sent to {phone_number}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending inactivity check to {phone_number}: {e}")
            return False
    
    async def send_nps_survey(self, phone_number: str) -> bool:
        """
        Envia pesquisa NPS.
        Chamado pelo scheduler nas sextas-feiras.
        """
        from app.services.whatsapp_onboarding import WhatsAppOnboarding
        
        try:
            onboarding = WhatsAppOnboarding()
            
            message = (
                "🎉 *Sextou!*\n\n"
                "Rapidinho: de *0 a 10*, qual a chance de você "
                "me indicar pra um amigo?\n\n"
                "_(Só digita o número)_\n\n"
                "E se quiser, conta: o que falta pra ser um *10*? 🚀"
            )
            
            await onboarding._send_text_message(phone_number, message)
            
            # Marca que enviamos NPS
            supabase.table("subscribers")\
                .update({"last_nps_at": datetime.utcnow().isoformat()})\
                .eq("phone_number", phone_number)\
                .execute()
            
            logger.info(f"NPS survey sent to {phone_number}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending NPS to {phone_number}: {e}")
            return False
    
    async def save_feedback(
        self, 
        subscriber_id: str, 
        feedback_type: str,
        score: int = None,
        comment: str = None,
        context: Dict = None
    ) -> bool:
        """
        Salva feedback no banco de dados.
        
        Args:
            subscriber_id: ID do subscriber
            feedback_type: 'nps', 'implicit', 'bug_report', 'feature_request', 'content_quality'
            score: Pontuação (0-10 para NPS, 1-3 para implicit)
            comment: Comentário do usuário
            context: Dados adicionais
        """
        try:
            supabase.table("feedback").insert({
                "subscriber_id": subscriber_id,
                "feedback_type": feedback_type,
                "score": score,
                "comment": comment,
                "context": context or {}
            }).execute()
            
            # Se for NPS, atualiza o score no subscriber
            if feedback_type == "nps" and score is not None:
                supabase.table("subscribers")\
                    .update({"nps_score": score})\
                    .eq("id", subscriber_id)\
                    .execute()
            
            logger.info(f"Feedback saved: {feedback_type} (score={score}) for {subscriber_id[:8]}...")
            return True
            
        except Exception as e:
            logger.error(f"Error saving feedback: {e}")
            return False
    
    async def process_feedback_response(
        self, 
        subscriber_id: str, 
        message: str,
        feedback_type: str = "implicit"
    ) -> Tuple[bool, str]:
        """
        Processa resposta de feedback do usuário.
        
        Returns:
            (is_feedback, response_message)
            - is_feedback: True se a mensagem foi identificada como feedback
            - response_message: Resposta a enviar ao usuário
        """
        message = message.strip()
        
        # Tenta extrair número
        score = None
        comment = None
        
        # Verifica se é um número
        try:
            score = int(message.split()[0])
            # O resto é comentário
            parts = message.split(maxsplit=1)
            if len(parts) > 1:
                comment = parts[1]
        except (ValueError, IndexError):
            # Não é número, é comentário
            comment = message
        
        # Salva o feedback
        await self.save_feedback(
            subscriber_id=subscriber_id,
            feedback_type=feedback_type,
            score=score,
            comment=comment,
            context={"raw_message": message}
        )
        
        # Gera resposta baseada no tipo
        if feedback_type == "nps":
            return True, self._get_nps_response(score)
        elif feedback_type == "implicit":
            return True, self._get_implicit_response(score)
        else:
            return True, "Obrigado pelo feedback! 💙"
    
    def _get_nps_response(self, score: Optional[int]) -> str:
        """Retorna resposta apropriada para NPS"""
        if score is None:
            return "Obrigado pelo feedback! Vou analisar com carinho. 💙"
        
        if score >= 9:
            return self.NPS_RESPONSES["promoter"]
        elif score >= 7:
            return self.NPS_RESPONSES["passive"]
        else:
            return self.NPS_RESPONSES["detractor"]
    
    def _get_implicit_response(self, score: Optional[int]) -> str:
        """Retorna resposta apropriada para feedback implícito"""
        if score in self.IMPLICIT_RESPONSES:
            return self.IMPLICIT_RESPONSES[score]
        return "Obrigado pelo feedback! Vou analisar. 💙"
    
    async def save_bug_report(
        self, 
        subscriber_id: str, 
        description: str,
        context: Dict = None
    ) -> bool:
        """Salva report de bug"""
        return await self.save_feedback(
            subscriber_id=subscriber_id,
            feedback_type="bug_report",
            comment=description,
            context=context
        )
    
    async def save_feature_request(
        self, 
        subscriber_id: str, 
        description: str
    ) -> bool:
        """Salva sugestão de feature"""
        return await self.save_feedback(
            subscriber_id=subscriber_id,
            feedback_type="feature_request",
            comment=description
        )
    
    async def get_pending_bugs(self, limit: int = 20) -> List[Dict]:
        """Retorna bugs não resolvidos"""
        try:
            response = supabase.table("feedback")\
                .select("*, subscribers(phone_number, name)")\
                .eq("feedback_type", "bug_report")\
                .eq("resolved", False)\
                .order("created_at", desc=True)\
                .limit(limit)\
                .execute()
            
            return response.data or []
            
        except Exception as e:
            logger.error(f"Error getting pending bugs: {e}")
            return []
    
    async def get_feedback_summary(self) -> Dict:
        """Retorna resumo de feedback"""
        try:
            # NPS médio
            nps_response = supabase.table("feedback")\
                .select("score")\
                .eq("feedback_type", "nps")\
                .not_.is_("score", "null")\
                .execute()
            
            nps_scores = [f["score"] for f in (nps_response.data or [])]
            avg_nps = sum(nps_scores) / len(nps_scores) if nps_scores else 0
            
            # Contagem por tipo
            all_feedback = supabase.table("feedback")\
                .select("feedback_type")\
                .execute()
            
            by_type = {}
            for f in (all_feedback.data or []):
                t = f["feedback_type"]
                by_type[t] = by_type.get(t, 0) + 1
            
            # Bugs não resolvidos
            bugs_response = supabase.table("feedback")\
                .select("id", count="exact")\
                .eq("feedback_type", "bug_report")\
                .eq("resolved", False)\
                .execute()
            
            return {
                "average_nps": round(avg_nps, 1),
                "total_nps_responses": len(nps_scores),
                "feedback_by_type": by_type,
                "unresolved_bugs": bugs_response.count or 0,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting feedback summary: {e}")
            return {}
    
    async def mark_bug_resolved(self, feedback_id: str) -> bool:
        """Marca bug como resolvido"""
        try:
            supabase.table("feedback")\
                .update({
                    "resolved": True,
                    "resolved_at": datetime.utcnow().isoformat()
                })\
                .eq("id", feedback_id)\
                .execute()
            
            return True
        except Exception as e:
            logger.error(f"Error marking bug resolved: {e}")
            return False


# Instância global
feedback_service = FeedbackService()
