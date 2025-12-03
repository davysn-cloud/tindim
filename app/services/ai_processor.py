import google.generativeai as genai
import json
import logging
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import List, Dict, Optional, Tuple
from app.config import settings
from app.core.prompts import SYSTEM_PROMPT_FINANCIAL_SUMMARY
from app.db.client import supabase

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURAÇÕES DE QUALIDADE DO PROCESSAMENTO
# =============================================================================

# Similaridade mínima para considerar artigos duplicados (0.0 a 1.0)
SIMILARITY_THRESHOLD = 0.75

# Número mínimo de bullet points esperados
MIN_BULLET_POINTS = 2

# Tamanho mínimo do headline
MIN_HEADLINE_LENGTH = 20

# Categorias válidas
VALID_CATEGORIES = [
    "TECH", "AGRO", "CRYPTO", "FINANCE", "BUSINESS", 
    "POLITICS", "SPORTS", "ENTERTAINMENT", "HEALTH", 
    "SCIENCE", "WORLD", "LIFESTYLE"
]

# Sentimentos válidos
VALID_SENTIMENTS = ["POSITIVO", "NEUTRO", "NEGATIVO"]

class AIProcessor:
    def __init__(self):
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        # Configurações de segurança relaxadas para conteúdo de notícias
        self.safety_settings = {
            genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
            genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_NONE,
            genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai.types.HarmBlockThreshold.BLOCK_NONE,
            genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
        }
        self.model = genai.GenerativeModel('gemini-2.5-flash', safety_settings=self.safety_settings)
        self._processed_headlines: List[str] = []  # Cache para deduplicação

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calcula similaridade entre dois textos usando SequenceMatcher"""
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

    def _is_duplicate(self, title: str, headline: str) -> bool:
        """
        Verifica se o artigo é duplicado baseado em título/headline.
        Compara com artigos já processados na sessão atual.
        """
        combined = f"{title} {headline}".lower()
        
        for existing in self._processed_headlines:
            if self._calculate_similarity(combined, existing) > SIMILARITY_THRESHOLD:
                return True
        
        return False

    def _validate_summary(self, summary: Dict) -> Tuple[bool, Optional[str]]:
        """
        Valida se o resumo gerado pela IA atende aos critérios de qualidade.
        Retorna (valido, motivo_rejeicao)
        """
        # 1. Verificar campos obrigatórios
        required_fields = ["headline", "bullet_points", "sentiment", "category"]
        for field in required_fields:
            if field not in summary:
                return False, f"campo '{field}' ausente"
        
        # 2. Verificar headline
        headline = summary.get("headline", "")
        if len(headline) < MIN_HEADLINE_LENGTH:
            return False, "headline muito curto"
        
        # 3. Verificar bullet points
        bullet_points = summary.get("bullet_points", [])
        if not isinstance(bullet_points, list) or len(bullet_points) < MIN_BULLET_POINTS:
            return False, "bullet points insuficientes"
        
        # 4. Verificar categoria válida
        category = summary.get("category", "")
        if category not in VALID_CATEGORIES:
            # Tentar corrigir categoria inválida
            summary["category"] = "BUSINESS"  # Fallback
        
        # 5. Verificar sentimento válido
        sentiment = summary.get("sentiment", "")
        if sentiment not in VALID_SENTIMENTS:
            summary["sentiment"] = "NEUTRO"  # Fallback
        
        return True, None

    def _calculate_relevance_score(self, article: Dict, summary: Dict) -> int:
        """
        Calcula um score de relevância para o artigo (0-100).
        Usado para priorizar artigos no envio.
        """
        score = 50  # Base
        
        # +10 se tiver muitos bullet points (conteúdo rico)
        bullet_points = summary.get("bullet_points", [])
        if len(bullet_points) >= 3:
            score += 10
        
        # +15 se for notícia recente (menos de 6 horas)
        try:
            published = article.get("published_at")
            if published:
                pub_time = datetime.fromisoformat(published.replace('Z', '+00:00'))
                hours_old = (datetime.utcnow().replace(tzinfo=pub_time.tzinfo) - pub_time).total_seconds() / 3600
                if hours_old < 6:
                    score += 15
                elif hours_old < 12:
                    score += 10
        except:
            pass
        
        # +10 se tiver sentimento definido (não neutro)
        if summary.get("sentiment") in ["POSITIVO", "NEGATIVO"]:
            score += 5
        
        # +15 se for de fonte premium (InfoMoney, Brazil Journal)
        url = article.get("url", "")
        if "infomoney.com" in url or "braziljournal.com" in url:
            score += 15
        
        # -20 se conteúdo original for muito curto
        content = article.get("original_content", "")
        clean_content = re.sub(r'<[^>]+>', '', content)
        if len(clean_content) < 500:
            score -= 20
        
        return max(0, min(100, score))  # Clamp entre 0-100

    async def process_pending_articles(self):
        logger.info("Buscando artigos pendentes de processamento IA...")
        
        # Limpar cache de headlines processados
        self._processed_headlines = []
        
        # Carregar headlines já processados nas últimas 24h para deduplicação
        from datetime import timedelta
        time_threshold = datetime.utcnow() - timedelta(hours=24)
        existing_response = supabase.table("articles")\
            .select("title, summary_json")\
            .gte("processed_at", time_threshold.isoformat())\
            .not_.is_("summary_json", "null")\
            .execute()
        
        for existing in existing_response.data:
            headline = existing.get("summary_json", {}).get("headline", "")
            self._processed_headlines.append(f"{existing['title']} {headline}".lower())
        
        logger.info(f"Cache de deduplicação: {len(self._processed_headlines)} artigos recentes")
        
        # Buscar artigos sem resumo
        response = supabase.table("articles").select("*").is_("summary_json", "null").execute()
        articles = response.data
        
        if not articles:
            logger.info("Nenhum artigo pendente.")
            return 0

        processed_count = 0
        skipped_duplicates = 0
        skipped_quality = 0
        
        for article in articles:
            try:
                title = article['title']
                content = article['original_content'][:5000]  # Limita caracteres
                
                content_to_process = f"Título: {title}\n\nConteúdo: {content}"
                
                # Chamada ao Gemini
                full_prompt = f"{SYSTEM_PROMPT_FINANCIAL_SUMMARY}\n\nARTIGO PARA ANALISAR:\n{content_to_process}"
                
                generation_config = genai.types.GenerationConfig(
                    temperature=0.2
                )
                
                try:
                    response = self.model.generate_content(full_prompt, generation_config=generation_config)
                    
                    # Verificar se foi bloqueado
                    if response.prompt_feedback and response.prompt_feedback.block_reason:
                        logger.warning(f"Artigo bloqueado pela IA: {title[:50]}...")
                        # Marcar como processado com erro para não tentar novamente
                        supabase.table("articles").update({
                            "processed_at": datetime.utcnow().isoformat(),
                            "summary_json": {"error": "blocked_by_safety"}
                        }).eq("id", article['id']).execute()
                        continue
                    
                    text_response = response.text
                except ValueError as e:
                    logger.warning(f"Erro de valor na resposta da IA para: {title[:50]}... - {e}")
                    supabase.table("articles").update({
                        "processed_at": datetime.utcnow().isoformat(),
                        "summary_json": {"error": "invalid_response"}
                    }).eq("id", article['id']).execute()
                    continue
                
                # Extrair JSON da resposta
                if "```json" in text_response:
                    text_response = text_response.split("```json")[1].split("```")[0]
                elif "```" in text_response:
                    text_response = text_response.split("```")[1].split("```")[0]
                
                summary_data = json.loads(text_response.strip())
                
                # Se retornou lista, pega o primeiro
                if isinstance(summary_data, list) and len(summary_data) > 0:
                    summary_data = summary_data[0]
                
                # VALIDAÇÃO DE QUALIDADE
                is_valid, rejection_reason = self._validate_summary(summary_data)
                if not is_valid:
                    logger.warning(f"Resumo rejeitado ({rejection_reason}): {title[:50]}...")
                    skipped_quality += 1
                    supabase.table("articles").update({
                        "processed_at": datetime.utcnow().isoformat(),
                        "summary_json": {"error": f"quality_check_failed: {rejection_reason}"}
                    }).eq("id", article['id']).execute()
                    continue
                
                # VERIFICAÇÃO DE DUPLICAÇÃO
                headline = summary_data.get("headline", "")
                if self._is_duplicate(title, headline):
                    logger.info(f"Artigo duplicado detectado: {title[:50]}...")
                    skipped_duplicates += 1
                    supabase.table("articles").update({
                        "processed_at": datetime.utcnow().isoformat(),
                        "summary_json": {"error": "duplicate"}
                    }).eq("id", article['id']).execute()
                    continue
                
                # CALCULAR SCORE DE RELEVÂNCIA
                relevance_score = self._calculate_relevance_score(article, summary_data)
                summary_data["relevance_score"] = relevance_score
                
                # Adicionar ao cache de deduplicação
                self._processed_headlines.append(f"{title} {headline}".lower())
                
                # Atualizar DB
                update_data = {
                    "summary_json": summary_data,
                    "processed_at": datetime.utcnow().isoformat(),
                    "category": summary_data.get("category", "BUSINESS")
                }
                
                supabase.table("articles").update(update_data).eq("id", article['id']).execute()
                processed_count += 1
                logger.info(f"Artigo processado (score={relevance_score}): {title[:50]}...")

            except json.JSONDecodeError as e:
                logger.error(f"Erro ao parsear JSON para artigo {article['id']}: {e}")
                supabase.table("articles").update({
                    "processed_at": datetime.utcnow().isoformat(),
                    "summary_json": {"error": "json_parse_error"}
                }).eq("id", article['id']).execute()
            except Exception as e:
                logger.error(f"Erro ao processar artigo {article['id']} com IA: {e}")
        
        logger.info(f"Processamento finalizado: {processed_count} processados, {skipped_duplicates} duplicados, {skipped_quality} rejeitados por qualidade")
        return processed_count
