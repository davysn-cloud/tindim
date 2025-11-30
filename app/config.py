import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Tindim"
    API_V1_STR: str = "/api/v1"
    
    # Supabase
    SUPABASE_URL: str
    SUPABASE_KEY: str
    
    # Google Gemini
    GOOGLE_API_KEY: str
    
    # WhatsApp
    WHATSAPP_API_TOKEN: str
    WHATSAPP_PHONE_NUMBER_ID: str
    WHATSAPP_VERIFY_TOKEN: str
    
    # ElevenLabs (opcional por enquanto)
    ELEVENLABS_API_KEY: str = "sua-elevenlabs-key"  # Temporário para testes
    ELEVENLABS_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"  # Voz padrão (Rachel)
    
    # App Config
    RSS_FEEDS: List[str] = [
        # Tech
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        # Finance
        "https://www.infomoney.com.br/feed/",
        "https://braziljournal.com/feed/",
        # Crypto
        "https://cointelegraph.com/rss",
        # Agro
        "https://www.canalrural.com.br/feed/",
    ]

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
