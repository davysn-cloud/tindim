import logging
import google.generativeai as genai
from datetime import datetime, timedelta
from typing import Optional, Dict
from app.config import settings
from app.db.client import supabase
from app.core.prompts import SYSTEM_PROMPT_CHAT_ASSISTANT

logger = logging.getLogger(__name__)

class ChatAssistantService:
    def __init__(self):
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        self.max_messages_per_conversation = 10

    async def process_user_message(self, phone_number: str, user_message: str) -> str:
        """
        Processa uma mensagem do usuário e retorna a resposta do assistente
        Gerencia o limite de 10 mensagens por conversa
        """
        logger.info(f"Processando mensagem de {phone_number}: {user_message}")
        
        # 1. Buscar ou criar assinante
        subscriber = await self._get_or_create_subscriber(phone_number)
        
        # 2. Verificar limite diário de mensagens
        if not await self._check_daily_limit(subscriber):
            return "Você atingiu o limite de conversas por hoje. Volte amanhã para mais interações! 😊"
        
        # 3. Buscar ou criar conversa ativa
        conversation = await self._get_or_create_conversation(subscriber["id"])
        
        # 4. Verificar limite de mensagens na conversa
        if conversation["message_count"] >= self.max_messages_per_conversation:
            # Encerrar conversa atual
            supabase.table("conversations")\
                .update({"is_active": False})\
                .eq("id", conversation["id"])\
                .execute()
            
            return "Você atingiu o limite de 10 mensagens nesta conversa. Envie uma nova mensagem para começar um novo tópico! 💬"
        
        # 5. Salvar mensagem do usuário
        await self._save_message(conversation["id"], "user", user_message)
        
        # 6. Buscar contexto (histórico + artigos relevantes)
        context = await self._build_context(conversation, subscriber, user_message)
        
        # 7. Gerar resposta com IA
        assistant_response = await self._generate_response(context, user_message)
        
        # 8. Salvar resposta do assistente
        await self._save_message(conversation["id"], "assistant", assistant_response)
        
        # 9. Atualizar contador de mensagens
        new_count = conversation["message_count"] + 2  # user + assistant
        supabase.table("conversations")\
            .update({
                "message_count": new_count,
                "last_message_at": datetime.utcnow().isoformat()
            })\
            .eq("id", conversation["id"])\
            .execute()
        
        # 10. Adicionar contador de mensagens restantes
        remaining = self.max_messages_per_conversation - new_count
        if remaining <= 3 and remaining > 0:
            assistant_response += f"\n\n_({remaining} mensagens restantes nesta conversa)_"
        
        return assistant_response

    async def _get_or_create_subscriber(self, phone_number: str) -> Dict:
        """Busca ou cria um assinante"""
        response = supabase.table("subscribers")\
            .select("*")\
            .eq("phone_number", phone_number)\
            .execute()
        
        if response.data:
            return response.data[0]
        
        # Criar novo assinante
        new_sub = {
            "phone_number": phone_number,
            "name": "Usuário",  # Nome padrão, pode ser atualizado depois
            "is_active": True,
            "interests": ["TECH", "FINANCE"]
        }
        
        result = supabase.table("subscribers").insert(new_sub).execute()
        return result.data[0]

    async def _check_daily_limit(self, subscriber: Dict) -> bool:
        """Verifica se o usuário ainda tem mensagens disponíveis no dia"""
        # Reset diário do contador
        last_reset = subscriber.get("last_reset_at")
        if last_reset:
            from datetime import timezone
            last_reset_date = datetime.fromisoformat(last_reset.replace('Z', '+00:00'))
            now_utc = datetime.now(timezone.utc)
            if (now_utc - last_reset_date).days >= 1:
                # Resetar contador
                supabase.table("subscribers")\
                    .update({
                        "daily_message_count": 0,
                        "last_reset_at": datetime.utcnow().isoformat()
                    })\
                    .eq("id", subscriber["id"])\
                    .execute()
                return True
        
        # Verificar limite (pode ajustar conforme necessário)
        daily_limit = 50  # Limite de mensagens por dia
        current_count = subscriber.get("daily_message_count", 0)
        
        if current_count >= daily_limit:
            return False
        
        # Incrementar contador
        supabase.table("subscribers")\
            .update({"daily_message_count": current_count + 1})\
            .eq("id", subscriber["id"])\
            .execute()
        
        return True

    async def _get_or_create_conversation(self, subscriber_id: str) -> Dict:
        """Busca conversa ativa ou cria uma nova"""
        response = supabase.table("conversations")\
            .select("*")\
            .eq("subscriber_id", subscriber_id)\
            .eq("is_active", True)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
        
        if response.data:
            return response.data[0]
        
        # Criar nova conversa
        new_conv = {
            "subscriber_id": subscriber_id,
            "message_count": 0,
            "is_active": True,
            "context": {}
        }
        
        result = supabase.table("conversations").insert(new_conv).execute()
        return result.data[0]

    async def _save_message(self, conversation_id: str, role: str, content: str):
        """Salva uma mensagem no histórico"""
        message_data = {
            "conversation_id": conversation_id,
            "role": role,
            "content": content
        }
        
        supabase.table("messages").insert(message_data).execute()

    async def _build_context(self, conversation: Dict, subscriber: Dict, user_message: str) -> str:
        """Constrói o contexto para a IA com histórico e artigos relevantes"""
        context = ""
        
        # 1. Buscar histórico de mensagens
        messages_response = supabase.table("messages")\
            .select("*")\
            .eq("conversation_id", conversation["id"])\
            .order("created_at")\
            .execute()
        
        if messages_response.data:
            context += "Histórico da conversa:\n"
            for msg in messages_response.data[-6:]:  # Últimas 6 mensagens
                role = "Usuário" if msg["role"] == "user" else "Assistente"
                context += f"{role}: {msg['content']}\n"
            context += "\n"
        
        # 2. Buscar artigos relevantes recentes
        interests = subscriber.get("interests", ["TECH", "FINANCE"])
        time_threshold = datetime.utcnow() - timedelta(days=2)
        
        articles_response = supabase.table("articles")\
            .select("*")\
            .gte("processed_at", time_threshold.isoformat())\
            .in_("category", interests)\
            .limit(5)\
            .execute()
        
        if articles_response.data:
            context += "Notícias recentes relevantes:\n"
            for article in articles_response.data:
                summary = article.get("summary_json", {})
                headline = summary.get("headline", article["title"])
                context += f"- {headline}\n"
                
                # Se a mensagem menciona palavras-chave do artigo, adicionar mais detalhes
                if any(word.lower() in user_message.lower() for word in headline.split()[:3]):
                    points = summary.get("bullet_points", [])
                    for point in points[:2]:
                        context += f"  • {point}\n"
            context += "\n"
        
        return context

    async def _generate_response(self, context: str, user_message: str) -> str:
        """Gera resposta usando IA"""
        full_prompt = f"{SYSTEM_PROMPT_CHAT_ASSISTANT}\n\n"
        full_prompt += f"Contexto:\n{context}\n"
        full_prompt += f"Mensagem do usuário: {user_message}\n\n"
        full_prompt += "Responda de forma útil e concisa:"
        
        generation_config = genai.types.GenerationConfig(
            temperature=0.7,
            max_output_tokens=500
        )
        
        try:
            response = self.model.generate_content(full_prompt, generation_config=generation_config)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Erro ao gerar resposta: {e}")
            return "Desculpe, tive um problema ao processar sua mensagem. Pode tentar novamente?"
