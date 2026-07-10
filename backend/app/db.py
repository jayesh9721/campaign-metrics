from supabase import create_client, Client
from app.config import settings

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client


def upsert(table: str, rows: list[dict], on_conflict: str) -> None:
    if not rows:
        return
    get_client().table(table).upsert(rows, on_conflict=on_conflict).execute()


def insert(table: str, rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    res = get_client().table(table).insert(rows).execute()
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
        client.table(table).insert(new_rows).execute()
