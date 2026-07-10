import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    supabase_url: str = os.environ.get("SUPABASE_URL", "")
    supabase_service_role_key: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    meta_access_token: str = os.environ.get("META_ACCESS_TOKEN", "")
    meta_ad_account_id: str = os.environ.get("META_AD_ACCOUNT_ID", "")

    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")

    google_ads_developer_token: str = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "")
    google_ads_client_id: str = os.environ.get("GOOGLE_ADS_CLIENT_ID", "")
    google_ads_client_secret: str = os.environ.get("GOOGLE_ADS_CLIENT_SECRET", "")
    google_ads_refresh_token: str = os.environ.get("GOOGLE_ADS_REFRESH_TOKEN", "")
    google_ads_customer_id: str = os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "")

    pipeline_trigger_secret: str = os.environ.get("PIPELINE_TRIGGER_SECRET", "")


settings = Settings()
