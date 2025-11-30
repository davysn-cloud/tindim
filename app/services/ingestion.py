import feedparser
import logging
from datetime import datetime
from dateutil import parser
from app.config import settings
from app.db.client import supabase

logger = logging.getLogger(__name__)

class IngestionService:
    def __init__(self):
        self.feeds = settings.RSS_FEEDS

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
                            
                    except Exception as e:
                        logger.error(f"Erro ao salvar artigo {link}: {e}")
                        continue
                        
            except Exception as e:
                logger.error(f"Erro ao processar feed {feed_url}: {e}")
                
        logger.info(f"Coleta finalizada. {new_articles_count} novos artigos salvos.")
        return new_articles_count
