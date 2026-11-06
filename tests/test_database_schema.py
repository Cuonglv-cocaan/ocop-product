import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb
import pandas as pd

from data import database as db


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        override = patch.object(db, "DUCKDB_PATH", Path(self.temp.name) / "test.duckdb")
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


if __name__ == "__main__":
    unittest.main()
