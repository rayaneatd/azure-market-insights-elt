import os
import polars as pl
from psycopg_pool import ConnectionPool
from psycopg.rows import namedtuple_row
from psycopg import sql
from enum import Enum
from typing import (
    Literal,
    Sequence,
    Mapping,
    Any
)

class DatabaseSchema(Enum):
    LOGS = "logs"


def _get_schema_name(schema: DatabaseSchema) -> str:
    return schema.value if isinstance(schema, Enum) else schema


def _execute(
    pool: ConnectionPool, 
    query: str | sql.SQL, 
    params: Sequence[Any] | Mapping[str, Any] | None = None
) -> None:
    """
    Executes a SQL query string or Composed SQL within a transaction using psycopg 3.
    
    Args:
        pool: The database connection pool.
        query: The SQL query string or sql.SQL object.
        params: The parameters (sequence or dict) to bind to the query.
    """
    with pool.connection() as conn:
        with conn.transaction():
            conn.execute(query, params) # pyrefly: ignore[bad-argument-type]


# function to execute sql queries from a string
def execute_sql_from_string(
    pool: ConnectionPool, 
    query: str | sql.SQL, 
    params: Sequence[Any] | Mapping[str, Any] | None = None
) -> None:
    """
    Executes a raw SQL string within a transaction.
    
    Args:
        pool: The database connection pool.
        query: The SQL query to execute.
        params: The parameters to use for the query.
    """
    _execute(pool, query, params)


# functions to execute sql queries from a file
def execute_sql_from_file(pool: ConnectionPool, path: str) -> None:
    """
    Reads a SQL file and executes it within a transaction.
    
    Args:
        pool: The database connection pool.
        path: The path to the SQL file.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"SQL file not found at: {path}")
    
    with open(path, "r", encoding="utf-8") as f:
        query_str = f.read()
    
    _execute(pool, query_str)


# function to read from the database
def read_from_db(pool: ConnectionPool, schema: DatabaseSchema, table: str) -> pl.DataFrame:
    """
    Reads a table from the database and returns a Polars DataFrame.
    
    Args:
        pool: The database connection pool.
        schema: The database schema.
        table: The table name.
    """
    schema_name = _get_schema_name(schema)
    
    query = sql.SQL("SELECT * FROM {}.{}").format(
        sql.Identifier(schema_name),
        sql.Identifier(table)
    )

    with pool.connection() as conn:
        query_str = query.as_string(conn)
        return pl.read_database(query_str, connection=conn)


# function to update/write into the database
def update_into_db(
    pool: ConnectionPool,
    schema: DatabaseSchema,
    table: str,
    df: pl.DataFrame,
    if_table_exists: Literal["append", "fail", "replace"] = "append"
) -> None:
    """
    Writes/updates a Polars DataFrame into the database.
    
    Args:
        pool: The database connection pool.
        schema: The database schema.
        table: The table name.
        df: The Polars DataFrame to write.
        if_table_exists: The action to take if the table already exists.
    """
    schema_name = _get_schema_name(schema)
    full_table_name = f"{schema_name}.{table}"

    with pool.connection() as conn:
        df.write_database(
            table_name=full_table_name,
            connection=conn,
            if_table_exists=if_table_exists
        )


# ================================================================
# Logging and Monitoring helper functions
# ================================================================

def start_ingestion_run(
    pool: ConnectionPool, 
    run_id: str, 
    error_message: str | None = None,
    layer: str | None = None
) -> None:
    """
    Logs the start of an orchestration run.
    
    Args:
        pool: The database connection pool.
        run_id: The run ID.
        error_message: Optional initial error message.
        layer: The pipeline layer name.
    """
    query = """
        INSERT INTO logs.ingestion_runs (run_id, started_at, status, error_message, layer)
        VALUES (%(run_id)s, CURRENT_TIMESTAMP, 'RUNNING', %(error_message)s, %(layer)s)
        ON CONFLICT (run_id) DO NOTHING;
    """
    _execute(pool, query, {"run_id": run_id, "error_message": error_message, "layer": layer})


def complete_ingestion_run(
    pool: ConnectionPool, 
    run_id: str, 
    status: Literal["COMPLETED", "FAILED"], 
    error_message: str | None = None
) -> None:
    """
    Logs the completion or failure of an orchestration run.
    
    Args:
        pool: The database connection pool.
        run_id: The run ID.
        status: The status of the run ('COMPLETED' or 'FAILED').
        error_message: The error message if failed.
    """
    query = """
        UPDATE logs.ingestion_runs
        SET completed_at = CURRENT_TIMESTAMP,
            status = %(status)s,
            error_message = %(error_message)s
        WHERE run_id = %(run_id)s;
    """
    _execute(pool, query, {
        "run_id": run_id,
        "status": status,
        "error_message": error_message
    })


def get_checkpoints(pool: ConnectionPool, layer: Literal["RAW", "ANALYTICS"] = "RAW") -> dict[str, dict]:
    """
    Retrieves all table checkpoints from Postgres.
    
    Args:
        pool: The database connection pool.
        layer: The pipeline layer ('RAW' or 'ANALYTICS').
    """
    query = """
        SELECT table_name, current_watermark, fallback_watermark, last_id, offset_val, is_override_active
        FROM logs.ingestion_checkpoints
        WHERE layer = %(layer)s;
    """
    
    with pool.connection() as conn:
        with conn.cursor(row_factory=namedtuple_row) as cur:
            cur.execute(query, {"layer": layer})
            
            return { 
                row.table_name: { # pyrefly: ignore 
                    "current_watermark": row.current_watermark, # pyrefly: ignore 
                    "fallback_watermark": row.fallback_watermark, # pyrefly: ignore 
                    "last_id": row.last_id, # pyrefly: ignore 
                    "offset_val": row.offset_val, # pyrefly: ignore 
                    "is_override_active": row.is_override_active # pyrefly: ignore 
                }
                for row in cur.fetchall()
            }


def upsert_checkpoint(
    pool: ConnectionPool,
    table_name: str,
    current_watermark: int,
    last_id: int,
    layer: Literal["RAW", "ANALYTICS"],
    offset_val: int,
    run_id: str | None,
    is_override_active: bool = False
) -> None:
    """
    Upserts checkpoint status for a table.
    
    Args:
        pool: The database connection pool.
        table_name: The table name.
        current_watermark: The current watermark timestamp.
        last_id: The last processed ID.
        layer: The pipeline layer.
        offset_val: The pagination offset value.
        run_id: The run ID.
        is_override_active: Whether override mode is active.
    """
    query = """
        INSERT INTO logs.ingestion_checkpoints (
            table_name, current_watermark, last_id, layer, offset_val, last_successful_run_id, is_override_active, updated_at
        )
        VALUES (
            %(table_name)s, %(current_watermark)s, %(last_id)s, %(layer)s, %(offset_val)s, %(run_id)s, %(is_override_active)s, CURRENT_TIMESTAMP
        )
        ON CONFLICT (table_name) DO UPDATE SET
            current_watermark = EXCLUDED.current_watermark,
            last_id = EXCLUDED.last_id,
            layer = EXCLUDED.layer,
            offset_val = EXCLUDED.offset_val,
            last_successful_run_id = EXCLUDED.last_successful_run_id,
            is_override_active = EXCLUDED.is_override_active,
            updated_at = CURRENT_TIMESTAMP;
    """
    _execute(pool, query, {
        "table_name": table_name,
        "current_watermark": current_watermark,
        "last_id": last_id,
        "layer": layer,
        "offset_val": offset_val,
        "run_id": run_id,
        "is_override_active": is_override_active
    })


def upsert_fallback_checkpoint(pool: ConnectionPool, table_name: str, fallback_watermark: int) -> None:
    """
    Updates the fallback/safety point for a table (when run succeeds entirely).
    
    Args:
        pool: The database connection pool.
        table_name: The table name.
        fallback_watermark: The fallback watermark timestamp.
    """
    query = """
        INSERT INTO logs.ingestion_checkpoints (table_name, fallback_watermark, updated_at)
        VALUES (%(table_name)s, %(fallback_watermark)s, CURRENT_TIMESTAMP)
        ON CONFLICT (table_name) DO UPDATE SET
            fallback_watermark = EXCLUDED.fallback_watermark,
            updated_at = CURRENT_TIMESTAMP;
    """
    _execute(pool, query, {
        "table_name": table_name,
        "fallback_watermark": fallback_watermark
    })


def log_batch(
    pool: ConnectionPool,
    run_id: str,
    table_name: str,
    layer: str,
    status: str,
    cursor_value: int,
    offset_value: int,
    records_count: int,
    duration_ms: int,
    query_sent: str,
    error_message: str | None = None
) -> None:
    """Logs an individual batch execution details."""
    query = """
        INSERT INTO logs.batch_logs (
            run_id, table_name, layer, status, cursor_value, offset_value, records_count, duration_ms, query_sent, error_message
        )
        VALUES (
            %(run_id)s, %(table_name)s, %(layer)s, %(status)s, %(cursor_value)s, %(offset_value)s, %(records_count)s, %(duration_ms)s, %(query_sent)s, %(error_message)s
        );
    """
    _execute(pool, query, {
        "run_id": run_id,
        "table_name": table_name,
        "layer": layer,
        "status": status,
        "cursor_value": cursor_value,
        "offset_value": offset_value,
        "records_count": records_count,
        "duration_ms": duration_ms,
        "query_sent": query_sent,
        "error_message": error_message
    })


def log_schema_change(
    pool: ConnectionPool,
    table_name: str,
    column_name: str,
    data_type: str,
    run_id: str,
    status: str = "NEW_COLUMN",
    action_taken: str | None = None
) -> None:
    """Logs schema changes or drifts found during parsing."""
    query = """
        INSERT INTO logs.schema_history (table_name, column_name, data_type, detected_in_run_id, status, action_taken)
        VALUES (%(table_name)s, %(column_name)s, %(data_type)s, %(run_id)s, %(status)s, %(action_taken)s)
        ON CONFLICT DO NOTHING;
    """
    _execute(pool, query, {
        "table_name": table_name,
        "column_name": column_name,
        "data_type": data_type,
        "run_id": run_id,
        "status": status,
        "action_taken": action_taken
    })


# ================================================================
# Fallback Event helper functions
# ================================================================

def get_pending_fallback_events(pool: ConnectionPool, layer: str = "RAW") -> list[dict[str, Any]]:
    """Retrieves pending fallback events in FIFO order."""
    query = """
        SELECT event_id::text, table_name, layer, start_watermark, end_watermark, status
        FROM logs.fallback_events
        WHERE status = 'PENDING' AND layer = %(layer)s
        ORDER BY created_at ASC;
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=namedtuple_row) as cur:
            cur.execute(query, {"layer": layer})
            return [
                {
                    "event_id": row.event_id,  # pyrefly: ignore
                    "table_name": row.table_name,  # pyrefly: ignore
                    "layer": row.layer,  # pyrefly: ignore
                    "start_watermark": row.start_watermark,  # pyrefly: ignore
                    "end_watermark": row.end_watermark,  # pyrefly: ignore
                    "status": row.status  # pyrefly: ignore
                }
                for row in cur.fetchall()
            ]


def update_fallback_event_status(
    pool: ConnectionPool,
    event_id: str,
    status: Literal["PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"],
    records_processed: int = 0,
    error_message: str | None = None
) -> None:
    """Updates status and metrics for a fallback event."""
    query = """
        UPDATE logs.fallback_events
        SET status = %(status)s,
            records_processed = records_processed + %(records_processed)s,
            error_message = %(error_message)s,
            completed_at = CASE WHEN %(status)s IN ('COMPLETED', 'FAILED') THEN CURRENT_TIMESTAMP ELSE completed_at END
        WHERE event_id = %(event_id)s::uuid;
    """
    _execute(pool, query, {
        "event_id": event_id,
        "status": status,
        "records_processed": records_processed,
        "error_message": error_message
    })