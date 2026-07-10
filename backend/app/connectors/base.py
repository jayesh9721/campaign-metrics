from abc import ABC, abstractmethod
from datetime import date


class PlatformConnector(ABC):
    # every method returns list[dict] keyed exactly to sql/schema.sql columns
    # (minus auto-generated id/created_at) — no platform-specific keys leak upward.

    @abstractmethod
    def fetch_campaigns(self) -> list[dict]: ...

    @abstractmethod
    def fetch_daily_metrics(self, since: date) -> list[dict]: ...

    @abstractmethod
    def fetch_budget_changes(self, since: date) -> list[dict]: ...

    @abstractmethod
    def fetch_audience_data(self, since: date) -> list[dict]: ...

    @abstractmethod
    def fetch_creative_data(self, since: date) -> list[dict]: ...
