import google.generativeai as genai
import json
import logging
from datetime import datetime
from app.config import settings
from app.core.prompts import SYSTEM_PROMPT_FINANCIAL_SUMMARY
from app.db.client import supabase

logger = logging.getLogger(__name__)

class AIProcessor:
    def __init__(self):
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    async def process_pending_articles(self):
        logger.info("Buscando artigos pendentes de processamento IA...")
        
        # Buscar artigos sem resumo
        # Supabase filter: summary_json is null
        response = supabase.table("articles").select("*").is_("summary_json", "null").execute()
        articles = response.data
        
        if not articles:
            logger.info("Nenhum artigo pendente.")
            return 0

        processed_count = 0
        
        for article in articles:
            try:
                content_to_process = f"Título: {article['title']}\n\nConteúdo: {article['original_content'][:5000]}" # Limita caracteres
                
                # Chamada ao Gemini
                full_prompt = f"{SYSTEM_PROMPT_FINANCIAL_SUMMARY}\n\nARTIGO PARA ANALISAR:\n{content_to_process}"
                
                generation_config = genai.types.GenerationConfig(
                    temperature=0.2
                )
                
                response = self.model.generate_content(full_prompt, generation_config=generation_config)
                
                # Extrair JSON da resposta (Gemini as vezes coloca markdown ```json ... ```)
                text_response = response.text
                if "```json" in text_response:
                    text_response = text_response.split("```json")[1].split("```")[0]
                elif "```" in text_response:
                    text_response = text_response.split("```")[1].split("```")[0]
                
                summary_data = json.loads(text_response.strip())
                
                # Se retornou lista, pega o primeiro (pois estamos enviando um por um)
                if isinstance(summary_data, list) and len(summary_data) > 0:
                    summary_data = summary_data[0]
                
                # Atualizar DB
                update_data = {
                    "summary_json": summary_data,
                    "processed_at": datetime.utcnow().isoformat(),
                    "category": summary_data.get("category", "GERAL")
                }
                
                supabase.table("articles").update(update_data).eq("id", article['id']).execute()
                processed_count += 1
                logger.info(f"Artigo processado: {article['title']}")

            except Exception as e:
                logger.error(f"Erro ao processar artigo {article['id']} com IA: {e}")
                # Opcional: Marcar erro no DB para não tentar sempre
                
        return processed_count
