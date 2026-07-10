import datetime

from supabase import create_client, Client
from app.config import settings

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client


def _jsonable(value):
    """postgrest-py hands rows straight to stdlib json.dumps, which doesn't
    know how to serialize date/datetime - connectors return those natively
    (e.g. Meta's start_date, launch_date), so normalize to ISO strings here
    rather than pushing this concern onto every connector."""
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def _clean_rows(rows: list[dict]) -> list[dict]:
    return [{k: _jsonable(v) for k, v in row.items()} for row in rows]


def upsert(table: str, rows: list[dict], on_conflict: str) -> None:
    if not rows:
        return
    get_client().table(table).upsert(_clean_rows(rows), on_conflict=on_conflict).execute()


def insert(table: str, rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    res = get_client().table(table).insert(_clean_rows(rows)).execute()
    return res.data


def insert_dedup(table: str, rows: list[dict], key_fields: list[str]) -> None:
    """For tables with no DB-level unique constraint (e.g. budget_change_log,
    where Meta's activity log could plausibly resurface the same event across
    overlapping ingestion windows) - skip rows that already match on key_fields
    rather than accumulating duplicates on every poll."""
    if not rows:
        return
    campaign_ids = list({r["campaign_id"] for r in rows if r.get("campaign_id")})
    if not campaign_ids:
        return
    client = get_client()
    existing = client.table(table).select(",".join(key_fields)).in_("campaign_id", campaign_ids).execute()
    existing_keys = {tuple(r.get(k) for k in key_fields) for r in existing.data}
    new_rows = [r for r in rows if tuple(r.get(k) for k in key_fields) not in existing_keys]
    if new_rows:
        client.table(table).insert(_clean_rows(new_rows)).execute()
