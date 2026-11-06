"""Safely merge crawler CSV into canonical OCOP CSV.

Example:
  python pipelines/sync_products.py --source TIKI --input crawlers/tiki/ocop_output/products_tiki.csv

- Preserve historical rows absent from new crawl
- Match records by (source, product_id)
- On matching rows, update only nonblank cells
- Backup existing master, then atomic replace
"""
from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MASTER = ROOT / "data/products_ocop.csv"
BACKUP_DIR = ROOT / "data/backups"
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Upsert TIKI/TikTok/Shopee CSV into OCOP master")
    parser.add_argument("--source", required=True, help="TIKI, TIKTOK, SHOPEE, etc.")
    parser.add_argument("--input", required=True, type=Path, help="CSV output file from crawler")
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER, help="Canonical CSV path")
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"Input CSV not found: {args.input}")
    source = args.source.strip().upper()
    if not source:
        parser.error("Source must not be blank. Master was NOT changed.")
    input_df = pd.read_csv(args.input, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if "product_id" not in input_df.columns and "id" not in input_df.columns:
        parser.error("Input needs 'product_id' or 'id' column")
    incoming = normalize(input_df, source)
    if incoming.empty:
        parser.error("No rows with valid product_id found. Master was NOT changed.")
    master_path = args.master.resolve()
    if master_path.exists():
        original = pd.read_csv(master_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if "product_id" not in original.columns and "id" not in original.columns:
            parser.error("Master CSV doesn't have a product_id/id column. No changes made.")
        master = normalize(original, None)
    else:
        master = pd.DataFrame(columns=COLUMNS)
    result, added, updated = merge(master, incoming)
    master_path.parent.mkdir(parents=True, exist_ok=True)
    if master_path.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup = BACKUP_DIR / f"products_ocop_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.csv"
        shutil.copy2(master_path, backup)
        print(f"Backup: {backup}")
    fd, temporary = tempfile.mkstemp(prefix=".products_ocop_", suffix=".csv", dir=master_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as output:
            result.to_csv(output, index=False)
        os.replace(temporary, master_path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    print(f"Source: {source} | Input rows: {len(incoming)} | Added: {added} | Updated: {updated} | Total: {len(result)}")
    print(f"Master: {master_path}")


if __name__ == "__main__":
    main()
