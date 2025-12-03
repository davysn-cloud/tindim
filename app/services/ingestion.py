import feedparser
import logging
import re
from datetime import datetime
from dateutil import parser
from typing import Optional, Tuple
from app.config import settings
from app.db.client import supabase

logger = logging.getLogger(__name__)

# =============================================================================
# FILTROS DE QUALIDADE - Palavras-chave para exclusão
# =============================================================================

# Títulos que indicam conteúdo de baixa relevância
LOW_VALUE_TITLE_PATTERNS = [
    # Loteria e jogos de azar
    r'\b(quina|lotof[aá]cil|mega[- ]?sena|lotomania|dupla[- ]?sena|timemania|loteria|sorteio|concurso \d+)\b',
    r'\b(resultado.*sorte|n[uú]meros.*sorteados|dezenas.*sorteadas)\b',
    # Horóscopo e astrologia
    r'\b(hor[oó]scopo|signos?.*hoje|previs[aã]o.*astrol[oó]gica)\b',
    # Conteúdo clickbait/vazio
    r'^(veja|confira|saiba)\s+(o que|como|quem|qual)',
    r'\b(n[aã]o vai acreditar|chocante|impressionante|voc[eê] precisa ver)\b',
    # Obituários
    r'\b(falece|morre|morte de|[oó]bito|velório|enterro|sepultamento)\b',
]

# Conteúdo que indica notícia de baixa qualidade
LOW_VALUE_CONTENT_PATTERNS = [
    r'as dezenas (do concurso|sorteadas)',
    r'(aposte|aposta|apostador|bilhete).*lot[eé]rica',
    r'pr[eê]mio.*acumulado',
    r'(caixa econ[oô]mica|cef).*sorteio',
]

# Tamanho mínimo de conteúdo (caracteres) - exclui artigos muito curtos
MIN_CONTENT_LENGTH = 200

# Tamanho mínimo de título
MIN_TITLE_LENGTH = 15

class IngestionService:
    def __init__(self):
        self.feeds = settings.RSS_FEEDS
        # Compilar padrões regex para performance
        self._title_patterns = [re.compile(p, re.IGNORECASE) for p in LOW_VALUE_TITLE_PATTERNS]
        self._content_patterns = [re.compile(p, re.IGNORECASE) for p in LOW_VALUE_CONTENT_PATTERNS]

    def _check_quality(self, title: str, content: str) -> Tuple[bool, Optional[str]]:
        """
        Verifica se o artigo passa nos filtros de qualidade.
        Retorna (passou, motivo_rejeicao)
        """
        # 1. Verificar tamanho mínimo do título
        if len(title.strip()) < MIN_TITLE_LENGTH:
            return False, "título muito curto"
        
        # 2. Verificar tamanho mínimo do conteúdo
        # Remove HTML tags para contagem mais precisa
        clean_content = re.sub(r'<[^>]+>', '', content)
        if len(clean_content.strip()) < MIN_CONTENT_LENGTH:
            return False, "conteúdo muito curto"
        
        # 3. Verificar padrões de título de baixa qualidade
        for pattern in self._title_patterns:
            if pattern.search(title):
                return False, f"título contém padrão de baixa relevância"
        
        # 4. Verificar padrões de conteúdo de baixa qualidade
        for pattern in self._content_patterns:
            if pattern.search(content):
                return False, f"conteúdo contém padrão de baixa relevância"
        
        return True, None

    async def fetch_and_store_news(self):
        logger.info("Iniciando coleta de notícias RSS...")
        new_articles_count = 0
        
        for feed_url in self.feeds:
            try:
                logger.info(f"Lendo feed: {feed_url}")
                feed = feedparser.parse(feed_url)
                
                for entry in feed.entries:
                    # Extrair dados básicos
                    title = entry.title
                    link = entry.link
                    content = ""
                    if 'content' in entry:
                        content = entry.content[0].value
                    elif 'summary' in entry:
                        content = entry.summary
                    else:
                        content = entry.title # Fallback
                    
                    published_at = datetime.utcnow()
                    if 'published' in entry:
                        try:
                            published_at = parser.parse(entry.published)
                        except:
                            pass

                    # FILTRO DE QUALIDADE - Verificar antes de salvar
                    passed, rejection_reason = self._check_quality(title, content)
                    if not passed:
                        logger.debug(f"Artigo rejeitado ({rejection_reason}): {title[:50]}...")
                        continue
                    
                    # Tentar inserir no banco (ignorando duplicatas via URL unique constraint)
                    try:
                        data = {
                            "title": title,
                            "url": link,
                            "original_content": content,
                            "published_at": published_at.isoformat(),
                            "processed_at": None # Marca como não processado
                        }
                        
                        # Verifica se já existe
                        existing = supabase.table("articles").select("id").eq("url", link).execute()
                        if not existing.data:
                            supabase.table("articles").insert(data).execute()
                            new_articles_count += 1
                            logger.debug(f"Artigo salvo: {title[:50]}...")
                            
                    except Exception as e:
                        logger.error(f"Erro ao salvar artigo {link}: {e}")
                        continue
                        
            except Exception as e:
                logger.error(f"Erro ao processar feed {feed_url}: {e}")
                
        logger.info(f"Coleta finalizada. {new_articles_count} novos artigos salvos.")
        return new_articles_count
