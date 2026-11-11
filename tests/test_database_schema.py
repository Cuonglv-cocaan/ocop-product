import tempfile
import os
import sqlite3
from contextlib import closing
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb
import pandas as pd

from data import database as db
from data import sqlite_leads


class SchemaTests(unittest.TestCase):
    def test_catalog_automatically_refreshes_and_can_be_overwritten(self):
        row = dict(source='TIKI', product_id='001', product_name='Tea')
        db.upsert_products(pd.DataFrame([row]))
        catalog = db.DUCKDB_PATH.with_name('catalog.duckdb')
        with duckdb.connect(str(catalog), read_only=True) as conn:
            self.assertEqual(conn.execute('SELECT product_name FROM products').fetchone()[0], 'Tea')
        db.upsert_products(pd.DataFrame([{**row, 'product_name': 'New tea'}]))
        db.export_catalog(catalog)
        with duckdb.connect(str(catalog), read_only=True) as conn:
            self.assertEqual(conn.execute('SELECT product_name FROM products').fetchone()[0], 'New tea')
            self.assertNotIn('leads', [r[0] for r in conn.execute('SHOW TABLES').fetchall()])

    def test_failed_export_preserves_existing_catalog_and_source(self):
        db.upsert_products(pd.DataFrame([dict(source='TIKI', product_id='001', product_name='Tea')]))
        catalog = db.DUCKDB_PATH.with_name('catalog.duckdb')
        before = catalog.read_bytes()
        with patch.object(db, '_write_catalog', side_effect=RuntimeError('Export failed')):
            with self.assertRaises(RuntimeError):
                db.upsert_products(pd.DataFrame([dict(source='TIKI', product_id='001', product_name='New tea')]))
        self.assertEqual(catalog.read_bytes(), before)
        self.assertEqual(db.read_products().iloc[0]['product_name'], 'New tea')
        with self.assertRaises(ValueError):
            db.export_catalog(db.DUCKDB_PATH)

    def setUp(self):
        backend = patch.dict(os.environ, {'LEADS_BACKEND': 'sqlite'})
        backend.start()
        self.addCleanup(backend.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        override = patch.object(db, "DUCKDB_PATH", Path(self.temp.name) / "test.duckdb")
        leads_override = patch.object(sqlite_leads, "SQLITE_LEADS_PATH", Path(self.temp.name) / "leads.sqlite3")
        leads_override.start()
        self.addCleanup(leads_override.stop)
        override.start()
        self.addCleanup(override.stop)

    def legacy_products(self, source="TIKI"):
        with db.connect() as conn:
            fields = ", ".join(f"{name} VARCHAR NOT NULL DEFAULT ''" for name in db.COLUMNS)
            conn.execute(f"CREATE TABLE products ({fields}, PRIMARY KEY(source, product_id))")
            conn.execute("INSERT INTO products (source,product_id) VALUES (?, '001')", [source])

    def test_constraints(self):
        with db.connect() as conn:
            db.initialize_products(conn)
            for source, product_id in [("", "001"), ("tiki", "001"), (" TIKI", "001"),
                                       ("TIKI", ""), ("TIKI", " "), ("TIKI", "001 ")]:
                with self.subTest(source=source, product_id=product_id), self.assertRaises(duckdb.ConstraintException):
                    conn.execute("INSERT INTO products (source,product_id) VALUES (?,?)", [source, product_id])
            with self.assertRaises(duckdb.ConstraintException):
                conn.execute("INSERT INTO products DEFAULT VALUES")

    def test_pipeline_normalizes_and_keeps_leading_zero(self):
        db.upsert_products(pd.DataFrame([dict(source=" tiki ", product_id=" 001 ", product_name="Tea")]))
        self.assertEqual(db.read_products().iloc[0]["product_id"], "001")
        self.assertEqual(db.read_products().iloc[0]["source"], "TIKI")

    def test_upgrade_preserves_rows_and_lead_sequence(self):
        self.legacy_products()
        first = db.save_lead("test", "Test", "test@example.com", "0", "Test")
        self.assertEqual(db.upgrade_products_schema(), 1)
        self.assertEqual(db.upgrade_products_schema(), 1)
        self.assertEqual(db.read_products().iloc[0]["product_id"], "001")
        self.assertEqual(db.save_lead("test", "Test", "test@example.com", "0", "Test"), first + 1)

    def test_invalid_legacy_data_rolls_back(self):
        self.legacy_products(source="tiki")
        with self.assertRaises(duckdb.ConstraintException):
            db.upgrade_products_schema()
        with db.connect() as conn:
            self.assertEqual(conn.execute("SELECT source FROM products").fetchone()[0], "tiki")
            self.assertNotIn("products_before_schema_upgrade", [r[0] for r in conn.execute("SHOW TABLES").fetchall()])

    def test_leads_never_open_duckdb(self):
        with patch.object(db, "connect", side_effect=AssertionError("DuckDB must not be opened")):
            lead_id = db.save_lead("buyer", " Name ", "a@example.com", "0", " Note ")
        with closing(db.connect_leads()) as conn:
            self.assertEqual(conn.execute("SELECT name, note FROM leads WHERE id=?", [lead_id]).fetchone(), ("Name", "Note"))
        self.assertFalse(db.DUCKDB_PATH.exists())

    def test_migrate_duckdb_leads_is_repeatable_and_exports_no_leads(self):
        with db.connect() as conn:
            db.initialize_products(conn)
            conn.execute("CREATE TABLE leads (id BIGINT, created_at TEXT, kind TEXT, name TEXT, email TEXT, phone TEXT, note TEXT)")
            conn.execute("INSERT INTO leads VALUES (7,'now','buyer','Name','a@example.com','0','Note')")
            conn.execute("CREATE TABLE ocop_embeddings_gemini (id VARCHAR PRIMARY KEY,text VARCHAR,embedding FLOAT[],metadata VARCHAR)")
            conn.execute("INSERT INTO ocop_embeddings_gemini VALUES ('v','test',[1.0,2.0],'{}')")
        self.assertEqual(db.migrate_duckdb_leads(), 1)
        self.assertEqual(db.migrate_duckdb_leads(), 0)
        destination = Path(self.temp.name) / "catalog.duckdb"
        db.export_catalog(destination)
        with duckdb.connect(str(destination), read_only=True) as conn:
            self.assertEqual({r[0] for r in conn.execute("SHOW TABLES").fetchall()}, {"products", "ocop_embeddings_gemini"})
            self.assertEqual(conn.execute("SELECT count(*) FROM ocop_embeddings_gemini").fetchall()[0][0], 1)

    def test_readonly_catalog_and_sqlite_leads(self):
        db.upsert_products(pd.DataFrame([dict(source="TIKI", product_id="001", product_name="Tea")]))
        with patch.object(db, "DUCKDB_READ_ONLY", True):
            self.assertEqual(len(db.read_products()), 1)
            self.assertGreater(db.save_lead("buyer", "Name", "a@example.com", "0", "Note"), 0)


if __name__ == "__main__":
    unittest.main()
