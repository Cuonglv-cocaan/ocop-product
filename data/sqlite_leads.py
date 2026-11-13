"""Legacy SQLite storage; retained until the explicit PostgreSQL cutover."""
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
leads_path = Path(os.getenv("SQLITE_LEADS_PATH", "data/leads.sqlite3")).expanduser()
SQLITE_LEADS_PATH = leads_path if leads_path.is_absolute() else PROJECT_ROOT / leads_path

def connect_leads():
    SQLITE_LEADS_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(SQLITE_LEADS_PATH), timeout=30)


def initialize_leads(connection):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            note TEXT NOT NULL,
            legacy_duckdb_id INTEGER UNIQUE
        )
    """)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(leads)")}
    if "legacy_duckdb_id" not in columns:
        connection.execute("ALTER TABLE leads ADD COLUMN legacy_duckdb_id INTEGER")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS leads_duckdb_id ON leads(legacy_duckdb_id)")


def save_lead(kind: str, name: str, email: str, phone: str, note: str) -> int:
    with closing(connect_leads()) as connection, connection:
        initialize_leads(connection)
        cursor = connection.execute(
            """INSERT INTO leads (created_at, kind, name, email, phone, note)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (datetime.now(timezone.utc).isoformat(), kind, name.strip(),
             email.strip(), phone.strip(), note.strip()),
        )
        return cursor.lastrowid


