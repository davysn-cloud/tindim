import httpx
import logging
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from datetime import datetime
from typing import List, Dict
from app.config import settings
from app.db.client import supabase
from app.core.prompts import SYSTEM_PROMPT_AUDIO_SCRIPT

logger = logging.getLogger(__name__)

class AudioGeneratorService:
    def __init__(self):
        self.elevenlabs_api_key = settings.ELEVENLABS_API_KEY
        self.elevenlabs_voice_id = settings.ELEVENLABS_VOICE_ID
        self.base_url = "https://api.elevenlabs.io/v1"
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        
        # Configurações de segurança relaxadas para permitir conteúdo de esportes/notícias
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        }
        
        self.model = genai.GenerativeModel('gemini-2.0-flash', safety_settings=self.safety_settings)

    async def generate_personalized_audio(self, subscriber_id: str) -> str:
        """
        Gera um áudio personalizado para um assinante específico
        Retorna a URL do áudio gerado
        """
        logger.info(f"Gerando áudio personalizado para subscriber {subscriber_id}")
        
        # 1. Buscar dados do assinante
        sub_response = supabase.table("subscribers").select("*").eq("id", subscriber_id).execute()
        if not sub_response.data:
            raise ValueError(f"Assinante {subscriber_id} não encontrado")
        
        subscriber = sub_response.data[0]
        user_name = subscriber["name"]
        interests = subscriber.get("interests", ["TECH", "FINANCE"])
        
        # 2. Buscar notícias relevantes (últimas 48h para garantir conteúdo)
        from datetime import timedelta
        time_threshold = datetime.utcnow() - timedelta(hours=48)
        
        articles_response = supabase.table("articles")\
            .select("*")\
            .gte("processed_at", time_threshold.isoformat())\
            .not_.is_("summary_json", "null")\
            .in_("category", interests)\
            .order("processed_at", desc=True)\
            .limit(10)\
            .execute()
        
        articles = articles_response.data
        
        # Fallback: se não houver artigos dos interesses, pega os mais recentes
        if not articles:
            logger.info(f"Sem artigos dos interesses de {user_name}, buscando mais recentes...")
            articles_response = supabase.table("articles")\
                .select("*")\
                .not_.is_("summary_json", "null")\
                .order("processed_at", desc=True)\
                .limit(8)\
                .execute()
            articles = articles_response.data
        
        if not articles:
            logger.info(f"Nenhuma notícia disponível para {user_name}")
            return None
        
        # 3. Gerar roteiro com IA
        script = await self._generate_script(user_name, articles, interests)
        
        # 4. Gerar áudio com ElevenLabs
        audio_url = await self._text_to_speech(script)
        
        # 5. Salvar no banco
        audio_data = {
            "subscriber_id": subscriber_id,
            "audio_url": audio_url,
            "script": script,
            "topics": interests,
            "created_at": datetime.utcnow().isoformat()
        }
        
        supabase.table("audio_digests").insert(audio_data).execute()
        
        logger.info(f"Áudio gerado com sucesso: {audio_url}")
        return audio_url

    async def _generate_script(self, user_name: str, articles: List[Dict], interests: List[str]) -> str:
        """Gera o roteiro do áudio usando IA"""
        
        # Agrupar artigos por categoria
        articles_by_category = {}
        for article in articles:
            cat = article.get("category", "GERAL")
            if cat not in articles_by_category:
                articles_by_category[cat] = []
            articles_by_category[cat].append(article)
        
        # Montar contexto para a IA
        context = f"Nome do usuário: {user_name}\n"
        context += f"Tópicos de interesse: {', '.join(interests)}\n\n"
        context += "Notícias do dia:\n\n"
        
        for category, cat_articles in articles_by_category.items():
            context += f"=== {category} ===\n"
            for article in cat_articles[:3]:  # Limita a 3 por categoria
                summary = article.get("summary_json", {})
                headline = summary.get("headline", article["title"])
                points = summary.get("bullet_points", [])
                
                context += f"- {headline}\n"
                for point in points[:2]:  # 2 pontos principais
                    context += f"  • {point}\n"
                context += "\n"
        
        # Gerar roteiro
        prompt = f"{SYSTEM_PROMPT_AUDIO_SCRIPT}\n\n{context}"
        
        generation_config = genai.types.GenerationConfig(
            temperature=0.7,
            max_output_tokens=800
        )
        
        try:
            response = self.model.generate_content(prompt, generation_config=generation_config)
            
            # Verifica se houve bloqueio por segurança
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                logger.warning(f"Script bloqueado por segurança: {response.prompt_feedback.block_reason}")
                # Gera script genérico de fallback
                return self._generate_fallback_script(user_name)
            
            return response.text.strip()
        except ValueError as e:
            logger.warning(f"Erro ao gerar script: {e}")
            return self._generate_fallback_script(user_name)
    
    def _generate_fallback_script(self, user_name: str) -> str:
        """Gera um script genérico quando o Gemini bloqueia - Tom witty"""
        return f"""
        Fala, {user_name}! Tudo certo? Aqui é o Tindim.
        
        Olha, hoje tem bastante coisa rolando. Dá uma olhada nas mensagens que te mandei no WhatsApp.
        
        Se quiser saber mais sobre alguma notícia, é só me chamar!
        
        Falou!
        """

    async def _text_to_speech(self, text: str) -> str:
        """
        Converte texto em áudio usando ElevenLabs
        Retorna a URL do áudio (pode ser salvo no Supabase Storage ou usar link direto)
        """
        url = f"{self.base_url}/text-to-speech/{self.elevenlabs_voice_id}"
        
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.elevenlabs_api_key
        }
        
        data = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.5,
                "use_speaker_boost": True
            }
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=data, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Erro ao gerar áudio: {response.text}")
                raise Exception(f"ElevenLabs API error: {response.status_code}")
            
            # Salvar áudio no Supabase Storage
            audio_bytes = response.content
            audio_url = await self._upload_to_storage(audio_bytes)
            
            return audio_url

    async def _upload_to_storage(self, audio_bytes: bytes) -> str:
        """
        Faz upload do áudio para o Supabase Storage
        Retorna a URL pública do arquivo
        """
        # Gerar nome único
        filename = f"audio_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.mp3"
        
        try:
            # Upload para Supabase Storage
            result = supabase.storage.from_("audio-digests").upload(
                filename,
                audio_bytes,
                {"content-type": "audio/mpeg"}
            )
            
            # Obter URL pública
            public_url = supabase.storage.from_("audio-digests").get_public_url(filename)
            
            return public_url
            
        except Exception as e:
            logger.error(f"Erro ao fazer upload do áudio: {e}")
            # Fallback: retornar URL temporária (você pode implementar outra estratégia)
            # Por exemplo, salvar localmente ou usar outro serviço
            raise

    async def broadcast_audio_digests(self):
        """Gera e envia áudios personalizados para todos os assinantes ativos"""
        from app.services.whatsapp import WhatsAppService
        
        logger.info("Iniciando geração de áudios personalizados...")
        
        # Buscar assinantes ativos
        subs_response = supabase.table("subscribers").select("*").eq("is_active", True).execute()
        subscribers = subs_response.data
        
        if not subscribers:
            logger.info("Nenhum assinante ativo.")
            return
        
        whatsapp_service = WhatsAppService()
        
        for sub in subscribers:
            try:
                # Gerar áudio personalizado
                audio_url = await self.generate_personalized_audio(sub["id"])
                
                if audio_url:
                    # Enviar via WhatsApp
                    success = await whatsapp_service.send_audio_message(
                        sub["phone_number"],
                        audio_url
                    )
                    
                    if success:
                        # Atualizar registro de envio
                        supabase.table("audio_digests")\
                            .update({"sent_at": datetime.utcnow().isoformat()})\
                            .eq("audio_url", audio_url)\
                            .execute()
                        
                        logger.info(f"Áudio enviado para {sub['name']}")
                
            except Exception as e:
                logger.error(f"Erro ao processar áudio para {sub['name']}: {e}")
        
        logger.info("Broadcast de áudios finalizado.")
    
    async def generate_demo_audio(self, headline: str) -> str:
        """
        Gera um áudio demo curto (15s) para demonstração no onboarding
        Retorna a URL do áudio gerado
        """
        logger.info(f"Gerando áudio demo para: {headline[:50]}...")
        
        # Script curto e impactante para demo
        demo_script = f"""
        Bom dia! Aqui é o Tindim, sua IA jornalista.
        
        A manchete do momento: {headline}
        
        Quer ouvir mais? Assine o plano Estrategista e receba áudios como esse todos os dias!
        """
        
        try:
            audio_url = await self._text_to_speech(demo_script.strip())
            return audio_url
        except Exception as e:
            logger.error(f"Erro ao gerar áudio demo: {e}")
            return None
