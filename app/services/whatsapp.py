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
        """Envia resumos de notícias personalizados por tópico para cada usuário"""
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
                    
                    # Filtrar artigos relevantes para este usuário
                    relevant_articles = []
                    for interest in interests:
                        if interest in articles_by_category:
                            relevant_articles.extend(articles_by_category[interest])
                    
                    if not relevant_articles:
                        logger.info(f"Nenhuma notícia relevante para {sub['phone_number']}")
                        continue
                    
                    # Montar mensagem personalizada
                    messages = self._build_personalized_messages(sub["name"], relevant_articles, interests)
                    
                    # Enviar mensagens
                    for msg_part in messages:
                        payload = {
                            "messaging_product": "whatsapp",
                            "to": sub["phone_number"],
                            "type": "text",
                            "text": {"body": msg_part}
                        }
                        
                        r = await client.post(self.base_url, headers=self.headers, json=payload)
                        if r.status_code not in [200, 201]:
                            logger.error(f"Falha ao enviar para {sub['phone_number']}: {r.text}")
                        else:
                            logger.info(f"Enviado para {sub['phone_number']}")
                        
                        await asyncio.sleep(1.0)
                    
                except Exception as e:
                    logger.error(f"Erro no envio para {sub['phone_number']}: {e}")

        logger.info("Broadcast finalizado.")

    def _build_personalized_messages(self, user_name: str, articles: List[Dict], interests: List[str]) -> List[str]:
        """Constrói mensagens personalizadas agrupadas por tópico"""
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
