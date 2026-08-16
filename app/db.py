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
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = OFF;")
        conn.executescript(schema_sql)

        # Migration helper for existing DBs if account_id is NOT NULL or account_username column is missing
        cursor.execute("PRAGMA table_info(jobs)")
        columns = cursor.fetchall()
        columns_dict = {col["name"]: col for col in columns}

        account_id_not_null = (
            "account_id" in columns_dict and columns_dict["account_id"]["notnull"] == 1
        )
        has_account_username = "account_username" in columns_dict

        if account_id_not_null or not has_account_username:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
                    account_username TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    result TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(url, account_id)
                );
                """
            )
            col_list = [c["name"] for c in columns]
            select_username = (
                "COALESCE(a.username, j.account_username)"
                if "account_username" in col_list
                else "a.username"
            )

            cursor.execute(
                f"""
                INSERT INTO jobs_new (id, url, account_id, account_username, status, result, attempts, created_at, updated_at)
                SELECT j.id, j.url, j.account_id, {select_username}, j.status, j.result, j.attempts, j.created_at, j.updated_at
                FROM jobs j
                LEFT JOIN accounts a ON j.account_id = a.id;
                """
            )
            cursor.execute("DROP TABLE jobs;")
            cursor.execute("ALTER TABLE jobs_new RENAME TO jobs;")

        cursor.execute("PRAGMA foreign_keys = ON;")
        conn.commit()
    finally:
        conn.close()
