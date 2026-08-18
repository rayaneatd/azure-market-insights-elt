from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from typing import Any
from werkzeug.security import generate_password_hash, check_password_hash

# Hardcoded accounts for debug & testing
HARDCODED_USERS = {
    "admin": {
        "password_hash": generate_password_hash("MyCrushsName@54"),
        "role": "ADMIN"
    },
    "visitor": {
        "password_hash": generate_password_hash("visitor123"),
        "role": "VIEWER"
    }
}


def authenticate_user_hardcoded(username: str, password: str) -> dict[str, Any] | None:
    """Validates user credentials against hardcoded test accounts."""
    username_clean = username.strip().lower()
    user = HARDCODED_USERS.get(username_clean)
    if user and check_password_hash(user["password_hash"], password):
        return {
            "username": username_clean,
            "role": user["role"]
        }
    return None


def get_dashboard_stats(pool: ConnectionPool) -> dict[str, Any]:
    """Retrieves high-level KPI metrics for the dashboard header."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM logs.ingestion_runs) AS total_runs,
                    (SELECT COUNT(*) FROM logs.ingestion_runs WHERE status = 'COMPLETED') AS successful_runs,
                    (SELECT COUNT(*) FROM logs.ingestion_runs WHERE status = 'FAILED') AS failed_runs,
                    (SELECT COUNT(*) FROM logs.ingestion_checkpoints) AS total_tables,
                    (SELECT COUNT(*) FROM logs.ingestion_checkpoints WHERE is_override_active = TRUE) AS active_overrides,
                    (SELECT COALESCE(SUM(records_count), 0) FROM logs.batch_logs) AS total_records_ingested,
                    (SELECT COUNT(*) FROM logs.schema_history) AS total_schema_changes
            """)
            row = cur.fetchone()
            return dict(row) if row else {}


def get_runs_history(pool: ConnectionPool, limit: int = 50) -> list[dict[str, Any]]:
    """Retrieves recent orchestration runs."""
    query = """
        SELECT run_id, started_at, completed_at, layer, status, error_message,
               EXTRACT(EPOCH FROM (completed_at - started_at))::INT AS duration_seconds
        FROM logs.ingestion_runs
        ORDER BY started_at DESC
        LIMIT %s;
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (limit,))
            return [dict(row) for row in cur.fetchall()]


def get_all_checkpoints(pool: ConnectionPool) -> list[dict[str, Any]]:
    """Retrieves state of all checkpoints."""
    query = """
        SELECT table_name, current_watermark, fallback_watermark, last_id, layer,
               offset_val, is_override_active, last_successful_run_id, updated_at
        FROM logs.ingestion_checkpoints
        ORDER BY table_name ASC;
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query)
            return [dict(row) for row in cur.fetchall()]


def set_checkpoint_override(
    pool: ConnectionPool,
    table_name: str,
    custom_watermark: int | None = None,
    activate_fallback: bool = True
) -> bool:
    """
    Triggers fallback override on a specific table checkpoint.
    """
    with pool.connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                if custom_watermark is not None:
                    cur.execute("""
                        UPDATE logs.ingestion_checkpoints
                        SET fallback_watermark = %s,
                            is_override_active = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE table_name = %s;
                    """, (custom_watermark, activate_fallback, table_name))
                else:
                    cur.execute("""
                        UPDATE logs.ingestion_checkpoints
                        SET is_override_active = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE table_name = %s;
                    """, (activate_fallback, table_name))
                return cur.rowcount > 0


def get_recent_batches(
    pool: ConnectionPool,
    limit: int = 100,
    table_name: str | None = None
) -> list[dict[str, Any]]:
    """Retrieves recent batch logs."""
    query = """
        SELECT batch_id, run_id, table_name, layer, status, cursor_value, offset_value,
               records_count, duration_ms, query_sent, error_message, created_at
        FROM logs.batch_logs
        WHERE (%s::VARCHAR IS NULL OR table_name = %s::VARCHAR)
        ORDER BY created_at DESC
        LIMIT %s;
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (table_name, table_name, limit))
            return [dict(row) for row in cur.fetchall()]


def get_schema_drifts(pool: ConnectionPool) -> list[dict[str, Any]]:
    """Retrieves schema history / column drift entries."""
    query = """
        SELECT id, table_name, column_name, data_type, detected_at,
               detected_in_run_id, included_at, status, action_taken
        FROM logs.schema_history
        ORDER BY detected_at DESC;
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query)
            return [dict(row) for row in cur.fetchall()]


def create_fallback_event(
    pool: ConnectionPool,
    table_name: str,
    start_watermark: int,
    end_watermark: int,
    layer: str = "RAW"
) -> dict[str, Any]:
    """Creates a new PENDING fallback event in logs.fallback_events."""
    query = """
        INSERT INTO logs.fallback_events (table_name, layer, start_watermark, end_watermark, status)
        VALUES (%s, %s, %s, %s, 'PENDING')
        RETURNING event_id::text, table_name, layer, start_watermark, end_watermark, status, created_at;
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (table_name, layer, start_watermark, end_watermark))
            return dict(cur.fetchone()) # pyrefly: ignore


def get_fallback_events(pool: ConnectionPool, limit: int = 50) -> list[dict[str, Any]]:
    """Retrieves fallback events queue history."""
    query = """
        SELECT event_id::text, table_name, layer, start_watermark, end_watermark,
               status, records_processed, error_message, created_at, completed_at
        FROM logs.fallback_events
        ORDER BY created_at DESC
        LIMIT %s;
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, (limit,))
            return [dict(row) for row in cur.fetchall()]
