import httpx
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List
from app.config import settings
from app.db.client import supabase

logger = logging.getLogger(__name__)

class WhatsAppService:
    def __init__(self):
        self.base_url = f"https://graph.facebook.com/v22.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        self.headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}",
            "Content-Type": "application/json"
        }

    async def broadcast_digest(self):
        """Envia resumos de notícias personalizados - UMA MENSAGEM POR TÓPICO"""
        logger.info("Iniciando broadcast personalizado via WhatsApp...")
        
        # 1. Buscar notícias processadas nas últimas 24 horas
        time_threshold = datetime.utcnow() - timedelta(hours=24)
        response = supabase.table("articles")\
            .select("*")\
            .gte("processed_at", time_threshold.isoformat())\
            .not_.is_("summary_json", "null")\
            .execute()
            
        articles = response.data
        if not articles:
            logger.info("Nenhuma notícia nova para enviar.")
            return

        # 2. Agrupar artigos por categoria
        articles_by_category: Dict[str, List] = {}
        for article in articles:
            category = article.get("category", "GERAL")
            if category not in articles_by_category:
                articles_by_category[category] = []
            articles_by_category[category].append(article)

        # 3. Buscar assinantes ativos
        subs_response = supabase.table("subscribers").select("*").eq("is_active", True).execute()
        subscribers = subs_response.data
        
        if not subscribers:
            logger.info("Nenhum assinante ativo.")
            return

        # 4. Enviar para cada assinante baseado em seus interesses
        async with httpx.AsyncClient(timeout=30.0) as client:
            for sub in subscribers:
                try:
                    # Obter interesses do usuário
                    interests = sub.get("interests", ["TECH", "FINANCE"])
                    if not isinstance(interests, list):
                        interests = ["TECH", "FINANCE"]
                    
                    # Verificar limite de mensagens do plano
                    plan = sub.get("plan", "generalista")
                    daily_limit = 10 if plan == "estrategista" else 5
                    current_count = sub.get("daily_message_count", 0)
                    
                    if current_count >= daily_limit:
                        logger.info(f"Limite diário atingido para {sub['phone_number']}")
                        continue
                    
                    # Enviar mensagem de boas-vindas
                    welcome_msg = self._build_welcome_message(sub["name"])
                    await self._send_message(client, sub["phone_number"], welcome_msg)
                    await asyncio.sleep(1.0)
                    
                    messages_sent = 0
                    
                    # Enviar UMA MENSAGEM POR TÓPICO
                    for interest in interests:
                        if interest not in articles_by_category:
                            continue
                        
                        if current_count + messages_sent >= daily_limit:
                            logger.info(f"Limite atingido para {sub['phone_number']}")
                            break
                        
                        # Monta mensagem para este tópico
                        topic_message = self._build_topic_message(
                            interest, 
                            articles_by_category[interest]
                        )
                        
                        success = await self._send_message(client, sub["phone_number"], topic_message)
                        if success:
                            messages_sent += 1
                        
                        await asyncio.sleep(1.5)  # Delay entre mensagens
                    
                    # Atualiza contador de mensagens
                    if messages_sent > 0:
                        supabase.table("subscribers")\
                            .update({"daily_message_count": current_count + messages_sent})\
                            .eq("id", sub["id"])\
                            .execute()
                        logger.info(f"Enviadas {messages_sent} mensagens para {sub['phone_number']}")
                    
                except Exception as e:
                    logger.error(f"Erro no envio para {sub['phone_number']}: {e}")

        logger.info("Broadcast finalizado.")

    def _build_welcome_message(self, user_name: str) -> str:
        """Mensagem de boas-vindas do dia"""
        return (
            f"📱 *Tindim* - {datetime.now().strftime('%d/%m/%Y')}\n\n"
            f"Bom dia, *{user_name}*! ☀️\n\n"
            f"Aqui estão suas notícias personalizadas de hoje. "
            f"Cada tópico será enviado em uma mensagem separada para facilitar a leitura.\n\n"
            f"💬 _Responda qualquer mensagem para saber mais!_"
        )

    def _build_topic_message(self, category: str, articles: List[Dict]) -> str:
        """Constrói UMA mensagem para UM tópico específico"""
        # Emoji por categoria
        category_emojis = {
            "TECH": "💻",
            "AGRO": "🌾",
            "CRYPTO": "₿",
            "FINANCE": "💰",
            "BUSINESS": "📊",
            "POLITICS": "🏛️",
            "SPORTS": "⚽",
            "ENTERTAINMENT": "🎬",
            "HEALTH": "🏥",
            "SCIENCE": "🔬",
            "GERAL": "📰"
        }
        
        emoji = category_emojis.get(category, "📰")
        msg = f"{emoji} *{category}*\n\n"
        
        # Limita a 3 artigos por tópico
        for article in articles[:3]:
            summary = article.get("summary_json", {})
            if not isinstance(summary, dict):
                summary = {}

            headline = summary.get("headline", article["title"])
            points = summary.get("bullet_points", [])
            if not isinstance(points, list):
                points = [str(points)]
                
            sentiment = summary.get("sentiment", "NEUTRO")
            icon = "🟢" if sentiment == "POSITIVO" else "🔴" if sentiment == "NEGATIVO" else "⚪"
            
            msg += f"{icon} *{headline}*\n"
            for p in points[:2]:  # Limita a 2 pontos por artigo
                msg += f"• {p}\n"
            msg += "\n"
        
        msg += f"_🤖 Gerado por IA via Tindim_"
        return msg

    async def _send_message(self, client: httpx.AsyncClient, phone_number: str, message: str) -> bool:
        """Envia uma mensagem via WhatsApp"""
        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": phone_number,
                "type": "text",
                "text": {"body": message}
            }
            
            r = await client.post(self.base_url, headers=self.headers, json=payload)
            if r.status_code not in [200, 201]:
                logger.error(f"Falha ao enviar para {phone_number}: {r.text}")
                return False
            return True
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem: {e}")
            return False

    def _build_personalized_messages(self, user_name: str, articles: List[Dict], interests: List[str]) -> List[str]:
        """Constrói mensagens personalizadas agrupadas por tópico (LEGADO)"""
        messages = []
        
        # Cabeçalho
        current_msg = f"📱 *Tindim* - {datetime.now().strftime('%d/%m/%Y')}\n"
        current_msg += f"Olá *{user_name}*! Aqui estão suas notícias de hoje:\n\n"
        
        # Agrupar por categoria
        articles_by_cat = {}
        for article in articles:
            cat = article.get("category", "GERAL")
            if cat not in articles_by_cat:
                articles_by_cat[cat] = []
            articles_by_cat[cat].append(article)
        
        # Emoji por categoria
        category_emojis = {
            "TECH": "💻",
            "AGRO": "🌾",
            "CRYPTO": "₿",
            "FINANCE": "💰",
            "BUSINESS": "📊",
            "POLITICS": "🏛️",
            "SPORTS": "⚽",
            "ENTERTAINMENT": "🎬",
            "HEALTH": "🏥",
            "SCIENCE": "🔬"
        }
        
        # Montar blocos por categoria
        for category in interests:
            if category not in articles_by_cat:
                continue
                
            emoji = category_emojis.get(category, "📰")
            category_block = f"{emoji} *{category}*\n\n"
            
            for article in articles_by_cat[category]:
                summary = article.get("summary_json", {})
                if not isinstance(summary, dict):
                    summary = {}

                headline = summary.get("headline", article["title"])
                points = summary.get("bullet_points", [])
                if not isinstance(points, list):
                    points = [str(points)]
                    
                sentiment = summary.get("sentiment", "NEUTRO")
                icon = "🟢" if sentiment == "POSITIVO" else "🔴" if sentiment == "NEGATIVO" else "⚪"
                
                article_block = f"{icon} *{headline}*\n"
                for p in points[:3]:  # Limita a 3 pontos
                    article_block += f"• {p}\n"
                article_block += "\n"
                
                # Verifica tamanho
                if len(current_msg) + len(category_block) + len(article_block) > 3000:
                    current_msg += "\n➡️ _Continua..._"
                    messages.append(current_msg)
                    current_msg = f"📱 *Tindim* (Parte {len(messages)+1})\n\n"
                    category_block = f"{emoji} *{category}* (continuação)\n\n"
                
                category_block += article_block
            
            current_msg += category_block
        
        current_msg += "💬 _Quer saber mais? Responda esta mensagem!_\n"
        current_msg += "🤖 _Gerado por IA via Tindim_"
        messages.append(current_msg)
        
        return messages

    async def send_text_message(self, phone_number: str, message: str):
        """Envia uma mensagem de texto simples"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "messaging_product": "whatsapp",
                "to": phone_number,
                "type": "text",
                "text": {"body": message}
            }
            
            r = await client.post(self.base_url, headers=self.headers, json=payload)
            if r.status_code not in [200, 201]:
                logger.error(f"Falha ao enviar mensagem: {r.text}")
                return False
            return True

    async def send_audio_message(self, phone_number: str, audio_url: str):
        """Envia uma mensagem de áudio"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "messaging_product": "whatsapp",
                "to": phone_number,
                "type": "audio",
                "audio": {"link": audio_url}
            }
            
            r = await client.post(self.base_url, headers=self.headers, json=payload)
            if r.status_code not in [200, 201]:
                logger.error(f"Falha ao enviar áudio: {r.text}")
                return False
            return True
