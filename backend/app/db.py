"""Cloud SQL for PostgreSQL access layer. Replaces the Supabase client -
GCP is now the single vendor for compute and data. Connects via the Cloud SQL
Python Connector (works identically from Cloud Run, Cloud Shell, or a local
dev machine - no Cloud SQL Auth Proxy binary or --add-cloudsql-instances
mount required)."""
from __future__ import annotations

import sqlalchemy
from google.cloud.sql.connector import Connector

from app.config import settings

_engine: sqlalchemy.engine.Engine | None = None
_connector: Connector | None = None


def get_engine() -> sqlalchemy.engine.Engine:
    global _engine, _connector
    if _engine is None:
        _connector = Connector()

        def getconn():
            return _connector.connect(
                settings.cloudsql_instance_connection_name,
                "pg8000",
                user=settings.cloudsql_db_user,
                password=settings.cloudsql_db_password,
                db=settings.cloudsql_db_name,
            )

        _engine = sqlalchemy.create_engine(
            "postgresql+pg8000://",
            creator=getconn,
            pool_size=5,
            max_overflow=2,
            pool_timeout=30,
            pool_recycle=1800,
        )
    return _engine


def query(sql: str, params: dict | None = None) -> list[dict]:
    with get_engine().connect() as conn:
        result = conn.execute(sqlalchemy.text(sql), params or {})
        return [dict(row._mapping) for row in result]


def execute(sql: str, params: dict | None = None) -> None:
    with get_engine().begin() as conn:
        conn.execute(sqlalchemy.text(sql), params or {})


def _normalize_rows(rows: list[dict]) -> tuple[list[str], list[dict]]:
    """Every row gets every column key (missing ones filled with None) so a
    single parametrized INSERT statement covers the whole batch."""
    columns = sorted({k for row in rows for k in row.keys()})
    normalized = [{c: row.get(c) for c in columns} for row in rows]
    return columns, normalized


def upsert(table: str, rows: list[dict], conflict_columns: list[str], update_columns: list[str] | None = None) -> None:
    """INSERT ... ON CONFLICT (conflict_columns) DO UPDATE SET ...

    update_columns lets a caller deliberately exclude columns from the update
    (e.g. jobs/detect.py re-upserts anomalies daily but must NOT clobber
    root_cause_label/root_cause_confidence that a later job already set) -
    defaults to every non-conflict column when omitted.
    """
    if not rows:
        return
    columns, normalized = _normalize_rows(rows)
    settable = update_columns if update_columns is not None else [c for c in columns if c not in conflict_columns]

    col_list = ", ".join(columns)
    placeholder_list = ", ".join(f":{c}" for c in columns)
    conflict_list = ", ".join(conflict_columns)
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in settable)

    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholder_list}) ON CONFLICT ({conflict_list})"
    sql += f" DO UPDATE SET {set_clause}" if set_clause else " DO NOTHING"

    with get_engine().begin() as conn:
        conn.execute(sqlalchemy.text(sql), normalized)


def insert(table: str, rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    columns, normalized = _normalize_rows(rows)
    col_list = ", ".join(columns)
    placeholder_list = ", ".join(f":{c}" for c in columns)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholder_list}) RETURNING *"

    inserted = []
    with get_engine().begin() as conn:
        for row in normalized:
            result = conn.execute(sqlalchemy.text(sql), row)
            inserted.append(dict(result.fetchone()._mapping))
    return inserted


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
    existing = query(
        f"SELECT {', '.join(key_fields)} FROM {table} WHERE campaign_id = ANY(:campaign_ids)",
        {"campaign_ids": campaign_ids},
    )
    existing_keys = {tuple(r.get(k) for k in key_fields) for r in existing}
    new_rows = [r for r in rows if tuple(r.get(k) for k in key_fields) not in existing_keys]
    if new_rows:
        insert(table, new_rows)
