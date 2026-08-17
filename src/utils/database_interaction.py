import os
import polars as pl
from sqlalchemy import text
from sqlalchemy.engine import Engine
from enum import Enum
from typing import Literal

class DatabaseSchema(Enum):
    LOGS = "logs"


def _get_schema_name(schema: DatabaseSchema) -> str:
    return schema.value if isinstance(schema, Enum) else schema



# function to execute sql queries from a string
def execute_sql_from_string(engine: Engine, query: str) -> None:
    """
    Executes a raw SQL string within a transaction.
    
    Args:
        engine: The database engine.
        query: The SQL query to execute.
    """

    
    with engine.begin() as conn:
        conn.execute(text(query))


# functions to execute sql queries
def execute_sql_from_file(engine: Engine, path: str) -> None:
    """
    Reads a SQL file and executes it within a transaction.
    
    Args:
        engine: The database engine.
        path: The path to the SQL file.
    """

    # check if the file exists
    if not os.path.exists(path):
        raise FileNotFoundError(f"SQL file not found at: {path}")
    
    # read the file
    with open(path, "r", encoding="utf-8") as f:
        sql = f.read()
    
    # execute the file
    execute_sql_from_string(engine, sql)


# function to read from the database
def read_from_db(engine: Engine, schema: DatabaseSchema, table: str) -> pl.DataFrame:
    """
    Reads a table from the database and returns a Polars DataFrame.
    
    Args:
        engine: The database engine.
        schema: The database schema.
        table: The table name.
    """
    
    schema_name = _get_schema_name(schema)
    query = f"SELECT * FROM {schema_name}.{table};"
    with engine.connect() as conn:
        return pl.read_database(query, connection=conn)


# function to update/write into the database
def update_into_db(
    engine: Engine,
    schema: DatabaseSchema,
    table: str,
    df: pl.DataFrame,
    if_table_exists: Literal["append", "fail", "replace"] = "append"
) -> None:
    """Writes/updates a Polars DataFrame into the database."""
    schema_name = _get_schema_name(schema)
    with engine.begin() as conn:
        df.write_database(
            table_name=f"{schema_name}.{table}",
            connection=conn,
            if_table_exists=if_table_exists
        )


# ================================================================
# Logging and Monitoring helper functions
# ================================================================

def start_ingestion_run(engine: Engine, run_id: str) -> None:
    """Logs the start of an orchestration run."""
    query = """
        INSERT INTO logs.ingestion_runs (run_id, started_at, status)
        VALUES (:run_id, CURRENT_TIMESTAMP, 'RUNNING')
        ON CONFLICT (run_id) DO NOTHING;
    """
    with engine.begin() as conn:
        conn.execute(text(query), {"run_id": run_id})


def complete_ingestion_run(engine: Engine, run_id: str, status: str, error_message: str | None = None) -> None:
    """Logs the completion or failure of an orchestration run."""
    query = """
        UPDATE logs.ingestion_runs
        SET completed_at = CURRENT_TIMESTAMP,
            status = :status,
            error_message = :error_message
        WHERE run_id = :run_id;
    """
    with engine.begin() as conn:
        conn.execute(text(query), {
            "run_id": run_id,
            "status": status,
            "error_message": error_message
        })


def get_checkpoints(engine: Engine) -> dict[str, dict]:
    """Retrieves all table checkpoints from Postgres."""
    query = """
        SELECT table_name, current_watermark, fallback_watermark, last_id, offset_val, is_override_active
        FROM logs.ingestion_checkpoints;
    """
    with engine.connect() as conn:
        result = conn.execute(text(query))
        return {
            row.table_name: {
                "current_watermark": row.current_watermark,
                "fallback_watermark": row.fallback_watermark,
                "last_id": row.last_id,
                "offset_val": row.offset_val,
                "is_override_active": row.is_override_active
            }
            for row in result
        }


def upsert_checkpoint(
    engine: Engine,
    table_name: str,
    current_watermark: int,
    last_id: int,
    offset_val: int,
    run_id: str | None,
    is_override_active: bool = False
) -> None:
    """Upserts checkpoint status for a table."""
    query = """
        INSERT INTO logs.ingestion_checkpoints (
            table_name, current_watermark, last_id, offset_val, last_successful_run_id, is_override_active, updated_at
        )
        VALUES (
            :table_name, :current_watermark, :last_id, :offset_val, :run_id, :is_override_active, CURRENT_TIMESTAMP
        )
        ON CONFLICT (table_name) DO UPDATE SET
            current_watermark = EXCLUDED.current_watermark,
            last_id = EXCLUDED.last_id,
            offset_val = EXCLUDED.offset_val,
            last_successful_run_id = EXCLUDED.last_successful_run_id,
            is_override_active = EXCLUDED.is_override_active,
            updated_at = CURRENT_TIMESTAMP;
    """
    with engine.begin() as conn:
        conn.execute(text(query), {
            "table_name": table_name,
            "current_watermark": current_watermark,
            "last_id": last_id,
            "offset_val": offset_val,
            "run_id": run_id,
            "is_override_active": is_override_active
        })


def upsert_fallback_checkpoint(engine: Engine, table_name: str, fallback_watermark: int) -> None:
    """Updates the fallback/safety point for a table (when run succeeds entirely)."""
    query = """
        INSERT INTO logs.ingestion_checkpoints (table_name, fallback_watermark, updated_at)
        VALUES (:table_name, :fallback_watermark, CURRENT_TIMESTAMP)
        ON CONFLICT (table_name) DO UPDATE SET
            fallback_watermark = EXCLUDED.fallback_watermark,
            updated_at = CURRENT_TIMESTAMP;
    """
    with engine.begin() as conn:
        conn.execute(text(query), {
            "table_name": table_name,
            "fallback_watermark": fallback_watermark
        })


def log_batch(
    engine: Engine,
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
            :run_id, :table_name, :layer, :status, :cursor_value, :offset_value, :records_count, :duration_ms, :query_sent, :error_message
        );
    """
    with engine.begin() as conn:
        conn.execute(text(query), {
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
    engine: Engine,
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
        VALUES (:table_name, :column_name, :data_type, :run_id, :status, :action_taken)
        ON CONFLICT DO NOTHING;
    """
    with engine.begin() as conn:
        conn.execute(text(query), {
            "table_name": table_name,
            "column_name": column_name,
            "data_type": data_type,
            "run_id": run_id,
            "status": status,
            "action_taken": action_taken
        })