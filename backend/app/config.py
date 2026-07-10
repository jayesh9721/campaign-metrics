import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Cloud SQL for PostgreSQL (replaces Supabase as the DB host - GCP is now
    # the single vendor for both compute and data per the project's decision).
    cloudsql_instance_connection_name: str = os.environ.get("CLOUDSQL_INSTANCE_CONNECTION_NAME", "")  # project:region:instance
    cloudsql_db_user: str = os.environ.get("CLOUDSQL_DB_USER", "")
    cloudsql_db_password: str = os.environ.get("CLOUDSQL_DB_PASSWORD", "")
    cloudsql_db_name: str = os.environ.get("CLOUDSQL_DB_NAME", "campaign_copilot")

    meta_access_token: str = os.environ.get("META_ACCESS_TOKEN", "")
    meta_ad_account_id: str = os.environ.get("META_AD_ACCOUNT_ID", "")

    # LLM routed through OpenRouter (OpenAI-compatible endpoint) rather than
    # calling Anthropic directly - see app/engine/llm_rationale.py.
    openrouter_api_key: str = os.environ.get("OPENROUTER_API_KEY", "")

    google_ads_developer_token: str = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "")
    google_ads_client_id: str = os.environ.get("GOOGLE_ADS_CLIENT_ID", "")
    google_ads_client_secret: str = os.environ.get("GOOGLE_ADS_CLIENT_SECRET", "")
    google_ads_refresh_token: str = os.environ.get("GOOGLE_ADS_REFRESH_TOKEN", "")
    google_ads_customer_id: str = os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "")

    # Shared secret so Cloud Scheduler's HTTP targets can call FastAPI job endpoints.
    pipeline_trigger_secret: str = os.environ.get("PIPELINE_TRIGGER_SECRET", "")


settings = Settings()
