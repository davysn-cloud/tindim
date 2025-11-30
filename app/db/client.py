from supabase import create_client, Client
from app.config import settings

def get_supabase_client() -> Client:
    url: str = settings.SUPABASE_URL
    key: str = settings.SUPABASE_KEY
    return create_client(url, key)

supabase: Client = get_supabase_client()
