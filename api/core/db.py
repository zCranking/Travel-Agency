from supabase import Client, create_client

from core.config import settings


def get_db() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_key)
