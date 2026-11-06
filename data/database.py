from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
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


COLUMNS = [
    "product_id", "product_name", "brand", "category_name", "province_name",
    "ocop_stars", "description", "source_url", "image_url", "price", "source",
]
ALIASES = {
    "id": "product_id", "name": "product_name", "title": "product_name",
    "seller": "brand", "category": "category_name",
    "category_level_2": "category_name", "province": "province_name",
    "province_hint": "province_name", "stars": "ocop_stars",
    "product_url": "source_url", "image": "image_url",
}


def nonblank(value: object) -> bool:
    return pd.notna(value) and str(value).strip() != ""


def normalize(df: pd.DataFrame, source: str | None) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip().str.lstrip("\ufeff")
    # Canonical fields take precedence if both canonical and legacy variants exist.
    for old, new in ALIASES.items():
        if old in df.columns:
            if new not in df.columns:
                df = df.rename(columns={old: new})
            else:
                df[new] = df[new].where(df[new].map(nonblank), df[old])
                df = df.drop(columns=[old])
    for name in COLUMNS:
        if name not in df.columns:
            df[name] = ""
    df = df[COLUMNS].fillna("").astype(str).apply(lambda c: c.str.strip())
    if source:
        df["source"] = source
    df["source"] = df["source"].str.strip().str.upper()
    df["province_name"] = df["province_name"].replace("", "Chưa cập nhật")
    # Product IDs are strings to retain leading zeros and long e-commerce IDs.
    df = df[(df["product_id"] != "") & (df["source"] != "")].copy()
    return df.drop_duplicates(["source", "product_id"], keep="last")


def merge(master: pd.DataFrame, incoming: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    current = master.set_index(["source", "product_id"], drop=False)
    added = updated = 0
    for (_, _), new_row in incoming.set_index(["source", "product_id"], drop=False).iterrows():
        key = (new_row["source"], new_row["product_id"])
        if key not in current.index:
            current.loc[key, COLUMNS] = new_row[COLUMNS].tolist()
            added += 1
        else:
            changed = False
            for field in COLUMNS:
                if field in ("source", "product_id"):
                    continue
                value = new_row[field]
                # Never replace a previously known value with a blank.
                # Unknown province marker shouldn't replace a known province.
                if field == "province_name" and value == "Chưa cập nhật":
                    continue
                if nonblank(value) and str(current.loc[key, field]) != str(value):
                    current.loc[key, field] = value
                    changed = True
            updated += int(changed)
    result = current.reset_index(drop=True)[COLUMNS]
    return result, added, updated


def initialize_products(connection):
    """Initialize shared tables from the single SQL schema definition."""
    connection.execute((BASE_DIR / "init_db.sql").read_text(encoding="utf-8"))


def upgrade_products_schema() -> int:
    """Apply current constraints to existing products atomically, preserving values.

    Invalid keys or dependent objects cause rollback; no rows are silently removed.
    """
    with connect() as connection:
        connection.begin()
        try:
            initialize_products(connection)
            actual = [row[1] for row in connection.execute("PRAGMA table_info('products')").fetchall()]
            if actual != COLUMNS:
                raise ValueError("Unexpected products columns; schema upgrade was not applied")
            connection.execute("ALTER TABLE products RENAME TO products_before_schema_upgrade")
            initialize_products(connection)
            fields = ", ".join(COLUMNS)
            connection.execute(f"INSERT INTO products ({fields}) SELECT {fields} FROM products_before_schema_upgrade")
            total = connection.execute("SELECT count(*) FROM products").fetchone()[0]
            connection.execute("DROP TABLE products_before_schema_upgrade")
            connection.commit()
            return total
        except Exception:
            connection.rollback()
            raise


def read_products() -> pd.DataFrame:
    """Read shared products directly from DuckDB without a CSV fallback."""
    with connect() as connection:
        initialize_products(connection)
        return connection.execute("SELECT * FROM products ORDER BY source, product_id").fetchdf()


def upsert_products(df: pd.DataFrame, source: str | None = None) -> tuple[int, int, int]:
    """Merge products atomically, preserving history and existing nonblank values."""
    incoming = normalize(df, source)
    if incoming.empty:
        raise ValueError("No products with valid source and product_id")
    with connect() as connection:
        connection.begin()
        try:
            initialize_products(connection)
            master = connection.execute("SELECT * FROM products").fetchdf()
            result, added, updated = merge(master, incoming)
            connection.register("merged_products", result)
            fields = ", ".join(COLUMNS)
            connection.execute(
                f"INSERT INTO products ({fields}) SELECT {fields} FROM merged_products "
                "ON CONFLICT (source, product_id) DO UPDATE SET "
                + ", ".join(f"{name} = excluded.{name}" for name in COLUMNS
                            if name not in ("source", "product_id"))
            )
            connection.commit()
            return added, updated, len(result)
        except Exception:
            connection.rollback()
            raise


def migrate_csv_products(path: Path, source: str | None = None) -> tuple[int, int, int]:
    """Import legacy/crawler CSV; keep the input file and allow safe reruns."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if not {"product_id", "id"}.intersection(df.columns):
        raise ValueError("Input needs a product_id/id column")
    if source is None and "source" not in df.columns:
        raise ValueError("Input needs a source column or an explicit source")
    return upsert_products(df, source)

def initialize_leads(connection):
    initialize_products(connection)


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

    parser = argparse.ArgumentParser(description="Migrate legacy data to shared DuckDB")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--migrate-sqlite", type=Path)
    actions.add_argument("--migrate-csv", type=Path)
    actions.add_argument("--upgrade-products-schema", action="store_true")
    parser.add_argument("--source", help="Override product source for crawler CSV")
    args = parser.parse_args()
    if args.upgrade_products_schema:
        print(f"Products schema upgraded. Rows preserved: {upgrade_products_schema()}")
    elif args.migrate_csv:
        added, updated, total = migrate_csv_products(args.migrate_csv, args.source)
        print(f"Products added: {added} | Updated: {updated} | Total: {total}")
        print(f"Database: {DUCKDB_PATH}")
    else:
        print(f"Migrated leads: {migrate_sqlite_leads(args.migrate_sqlite)}")
