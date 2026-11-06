import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import DuckDB

from data import database as db
from src import vectorization as v


class FakeEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[1.0, float(len(text))] for text in texts]

    def embed_query(self, text):
        return [1.0, float(len(text))]


class VectorizationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        override = patch.object(db, "DUCKDB_PATH", Path(self.temp.name) / "test.duckdb")
        override.start()
        self.addCleanup(override.stop)
        db.upsert_products(pd.DataFrame([
            dict(source="TIKI", product_id="001", product_name="Tea", description="long description " * 200),
            dict(source="OTHER", product_id="001", product_name="Other tea"),
        ]))
        self.conn = db.connect()
        self.addCleanup(self.conn.close)
        self.store = DuckDB(connection=self.conn, embedding=FakeEmbeddings(), table_name=v.VECTOR_TABLE)
        mock = patch.object(v, "get_vector_store", new=AsyncMock(return_value=self.store))
        mock.start()
        self.addCleanup(mock.stop)

    async def test_database_default_and_repeat(self):
        first = await v.run_vectorize_async(batch_size=2)
        second = await v.run_vectorize_async(batch_size=2)
        self.assertEqual(first["products"], 2)
        self.assertEqual(first["files"], 0)
        self.assertEqual(first["chunks"], second["chunks"])
        count = self.conn.execute(f"SELECT count(*), count(DISTINCT id) FROM {v.VECTOR_TABLE}").fetchall()[0]
        self.assertEqual(count, (first["chunks"], first["chunks"]))
        docs = self.store.similarity_search("tea", k=1)
        self.assertIn(docs[0].metadata["source"], ("TIKI", "OTHER"))
        self.assertEqual(docs[0].metadata["product_id"], "001")

    async def test_shorter_description_removes_old_chunks_only_for_source(self):
        await v.run_vectorize_async()
        db.upsert_products(pd.DataFrame([dict(source="TIKI", product_id="001", description="Short")]))
        stats = await v.run_vectorize_async(source=" tiki ")
        self.assertEqual(stats["products"], 1)
        self.assertEqual(stats["chunks"], 1)
        self.assertEqual(self.conn.execute(f"SELECT count(*) FROM {v.VECTOR_TABLE}").fetchone()[0], 2)

    async def test_embedding_failure_keeps_old_vectors(self):
        await v.run_vectorize_async()
        before = self.conn.execute(f"SELECT * FROM {v.VECTOR_TABLE} ORDER BY id").fetchall()
        with patch.object(self.store.embeddings, "embed_documents", side_effect=RuntimeError("API failed")):
            with self.assertRaises(RuntimeError):
                await v.run_vectorize_async()
        self.assertEqual(before, self.conn.execute(f"SELECT * FROM {v.VECTOR_TABLE} ORDER BY id").fetchall())

    async def test_invalid_vectors_keep_old_vectors(self):
        await v.run_vectorize_async()
        before = self.conn.execute(f"SELECT * FROM {v.VECTOR_TABLE} ORDER BY id").fetchall()
        with patch.object(self.store.embeddings, "embed_documents", side_effect=lambda texts: [[float("nan")] for _ in texts]):
            with self.assertRaises(ValueError):
                await v.run_vectorize_async()
        self.assertEqual(before, self.conn.execute(f"SELECT * FROM {v.VECTOR_TABLE} ORDER BY id").fetchall())

    async def test_validation(self):
        for size in [0, -1, True, 1.5]:
            with self.subTest(size=size), self.assertRaises(ValueError):
                await v.run_vectorize_async(batch_size=size)
        with self.assertRaises(ValueError):
            await v.run_vectorize_async(source=" ")
        with self.assertRaises(ValueError):
            await v.run_vectorize_async(source="MISSING")

    async def test_csv_import(self):
        csv = Path(self.temp.name) / "input.csv"
        csv.write_text("id,name,price\n002,New tea,100\n", encoding="utf-8")
        stats = await v.run_vectorize_async(str(csv), source="tiki")
        self.assertEqual(stats["added"], 1)
        self.assertEqual(stats["products"], 1)
        self.assertEqual(stats["total_products"], 3)


if __name__ == "__main__":
    unittest.main()
