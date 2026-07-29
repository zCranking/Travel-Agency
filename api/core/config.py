from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_service_key: str = ""
    anthropic_api_key: str = ""
    voyage_api_key: str = ""

    # Empty token => MockDuffelClient. A `duffel_test_*` token books against
    # Duffel's test airlines (no money, no real tickets). A `duffel_live_*`
    # token spends real money, so it additionally requires the explicit
    # opt-in below before any order is created.
    duffel_access_token: str = ""
    duffel_allow_live_booking: bool = False


settings = Settings()
