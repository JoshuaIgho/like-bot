import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = os.getenv("DB_PATH", "bot.db")


def get_db_path() -> str:
    return os.getenv("DB_PATH", DEFAULT_DB_PATH)


def get_db_connection(db_path: str | None = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db(db_path: str | None = None) -> None:
    if db_path is None:
        db_path = get_db_path()
    schema_path = Path(__file__).parent / "schemas.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = get_db_connection(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()
