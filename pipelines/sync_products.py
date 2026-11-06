"""Merge crawler CSV into the shared DuckDB products table."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.database import DUCKDB_PATH, migrate_csv_products


def main() -> None:
    parser = argparse.ArgumentParser(description="Upsert crawler products into shared DuckDB")
    parser.add_argument("--source", required=True, help="TIKI, TIKTOK, SHOPEE, etc.")
    parser.add_argument("--input", required=True, type=Path, help="Crawler CSV input")
    args = parser.parse_args()
    source = args.source.strip().upper()
    if not source:
        parser.error("Source must not be blank")
    if not args.input.is_file():
        parser.error(f"Input CSV not found: {args.input}")
    try:
        added, updated, total = migrate_csv_products(args.input, source)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Source: {source} | Added: {added} | Updated: {updated} | Total: {total}")
    print(f"Database: {DUCKDB_PATH}")


if __name__ == "__main__":
    main()