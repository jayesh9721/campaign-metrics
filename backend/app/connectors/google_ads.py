from datetime import date

from .base import PlatformConnector


class GoogleAdsConnector(PlatformConnector):
    # constructor accepts full credential set now so wiring this in later is
    # just filling in method bodies, no signature churn upstream.
    def __init__(
        self,
        developer_token: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        customer_id: str,
    ) -> None:
        self.developer_token = developer_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.customer_id = customer_id

    def fetch_campaigns(self) -> list[dict]:
        raise NotImplementedError("Google Ads connector pending API access confirmation")

    def fetch_daily_metrics(self, since: date) -> list[dict]:
        raise NotImplementedError("Google Ads connector pending API access confirmation")

    def fetch_budget_changes(self, since: date) -> list[dict]:
        raise NotImplementedError("Google Ads connector pending API access confirmation")

    def fetch_audience_data(self, since: date) -> list[dict]:
        raise NotImplementedError("Google Ads connector pending API access confirmation")

    def fetch_creative_data(self, since: date) -> list[dict]:
        raise NotImplementedError("Google Ads connector pending API access confirmation")
