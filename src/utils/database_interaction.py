from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool
from enum import Enum

class DatabaseSchema(Enum):
    LOGS = "logs"


def _get_schema_name(schema: DatabaseSchema) -> str:
    return schema.value if isinstance(schema, Enum) else schema

    # functions to execute sql queries
def execute_sql_from_file(engine: Engine, path: str):
    pass

    # function to execute sql queries from a string
def execute_sql_from_string(engine: Engine, query: str):
    pass

    # function to read from the database
def read_from_db(engine: Engine, schema: DatabaseSchema, table: str):
    pass

    # function to update the database
def update_into_db(engine: Engine, schema: DatabaseSchema, table: str):
    pass