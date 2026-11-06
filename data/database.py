from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb
from dotenv import load_dotenv

if TYPE_CHECKING:
    from langchain_community.vectorstores import DuckDB


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

# Environment variables take precedence over the project's local .env.
load_dotenv(PROJECT_ROOT / ".env")

db_path = Path(
    os.getenv("DUCKDB_PATH", "data/ocop.duckdb")
).expanduser()

if not db_path.is_absolute():
    db_path = PROJECT_ROOT / db_path

DUCKDB_PATH = db_path


def connect():
    DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DUCKDB_PATH))


def initialize_leads(connection):
    connection.execute("CREATE SEQUENCE IF NOT EXISTS lead_ids START 1")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id BIGINT PRIMARY KEY DEFAULT nextval('lead_ids'),
            created_at TEXT NOT NULL,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            note TEXT NOT NULL,
            legacy_sqlite_id BIGINT UNIQUE
        )
    """)


def save_lead(kind: str, name: str, email: str, phone: str, note: str) -> int:
    with connect() as connection:
        initialize_leads(connection)
        row = connection.execute(
            """INSERT INTO leads (created_at, kind, name, email, phone, note)
               VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
            (datetime.now(timezone.utc).isoformat(), kind, name.strip(),
             email.strip(), phone.strip(), note.strip()),
        ).fetchone()
        return row[0]


def migrate_sqlite_leads(path: Path = BASE_DIR / "leads.sqlite3") -> int:
    """Copy legacy leads once per legacy ID, leaving the SQLite file intact."""
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as legacy:
        rows = legacy.execute(
            "SELECT id, created_at, kind, name, email, phone, note FROM leads"
        ).fetchall()
    with connect() as connection:
        connection.begin()
        try:
            initialize_leads(connection)
            added = 0
            for legacy_id, *values in rows:
                if connection.execute(
                    "SELECT 1 FROM leads WHERE legacy_sqlite_id = ?", [legacy_id]
                ).fetchone():
                    continue
                connection.execute(
                    """INSERT INTO leads
                       (created_at, kind, name, email, phone, note, legacy_sqlite_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""", [*values, legacy_id]
                )
                added += 1
            connection.commit()
            return added
        except Exception:
            connection.rollback()
            raise


@lru_cache(maxsize=1)
def _get_vector_store() -> DuckDB:
    """Khởi tạo và tái sử dụng vector store trong một tiến trình."""
    from langchain_community.vectorstores import DuckDB
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    api_key = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    )

    if not api_key:
        raise RuntimeError(
            "Chưa cấu hình GEMINI_API_KEY hoặc GOOGLE_API_KEY."
        )

    DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)

    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=api_key,
    )

    connection = duckdb.connect(str(DUCKDB_PATH))

    try:
        return DuckDB(
            connection=connection,
            embedding=embeddings,
            table_name="ocop_embeddings_gemini",
        )
    except Exception:
        connection.close()
        raise


async def get_vector_store() -> DuckDB:
    """Giữ cách gọi tương thích với pipeline hiện tại."""
    return _get_vector_store()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate legacy SQLite leads to DuckDB")
    parser.add_argument("--migrate-sqlite", type=Path, required=True)
    args = parser.parse_args()
    print(f"Migrated leads: {migrate_sqlite_leads(args.migrate_sqlite)}")
