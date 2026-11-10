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
        wait = patch.object(v, "_wait")
        wait.start()
        self.addCleanup(wait.stop)
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
        self.assertEqual(second["chunks"], 0)
        self.assertEqual(second["skipped"], 2)
        count = self.conn.execute(f"SELECT count(*), count(DISTINCT id) FROM {v.VECTOR_TABLE}").fetchall()[0]
        self.assertEqual(count, (first["chunks"], first["chunks"]))
        import duckdb
        with duckdb.connect(str(db.DUCKDB_PATH.with_name('catalog.duckdb')), read_only=True) as catalog:
            self.assertEqual(catalog.execute(f'SELECT count(*) FROM {v.VECTOR_TABLE}').fetchone()[0], first['chunks'])
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
                await v.run_vectorize_async(force=True)
        self.assertEqual(before, self.conn.execute(f"SELECT * FROM {v.VECTOR_TABLE} ORDER BY id").fetchall())

    async def test_invalid_vectors_keep_old_vectors(self):
        await v.run_vectorize_async()
        before = self.conn.execute(f"SELECT * FROM {v.VECTOR_TABLE} ORDER BY id").fetchall()
        with patch.object(self.store.embeddings, "embed_documents", side_effect=lambda texts: [[float("nan")] for _ in texts]):
            with self.assertRaises(ValueError):
                await v.run_vectorize_async(force=True)
        self.assertEqual(before, self.conn.execute(f"SELECT * FROM {v.VECTOR_TABLE} ORDER BY id").fetchall())

    async def test_validation(self):
        for size in [0, -1, True, 1.5]:
            with self.subTest(size=size), self.assertRaises(ValueError):
                await v.run_vectorize_async(batch_size=size)
        with self.assertRaises(ValueError):
            await v.run_vectorize_async(source=" ")
        with self.assertRaises(ValueError):
            await v.run_vectorize_async(source="MISSING")

    def test_rate_limit_retries_server_delay(self):
        with patch.object(self.store.embeddings, "embed_documents", side_effect=[
            RuntimeError("429 RESOURCE_EXHAUSTED Please retry in 58.265s."), [[1.0, 2.0]]
        ]) as embed:
            self.assertEqual(v._embed_with_retry(self.store.embeddings, ["Tea"]), [[1.0, 2.0]])
            self.assertEqual(embed.call_count, 2)
            v._wait.assert_called_once_with(60.265)

    def test_rate_limit_stops_after_three_retries(self):
        with patch.object(self.store.embeddings, "embed_documents", side_effect=RuntimeError("429 RESOURCE_EXHAUSTED")) as embed:
            with self.assertRaises(RuntimeError):
                v._embed_with_retry(self.store.embeddings, ["Tea"])
            self.assertEqual(embed.call_count, 4)

    async def test_csv_import(self):
        csv = Path(self.temp.name) / "input.csv"
        csv.write_text("id,name,price\n002,New tea,100\n", encoding="utf-8")
        stats = await v.run_vectorize_async(str(csv), source="tiki")
        self.assertEqual(stats["added"], 1)
        self.assertEqual(stats["products"], 1)
        self.assertEqual(stats["total_products"], 3)

    async def test_unchanged_skips_api_and_store_setup(self):
        await v.run_vectorize_async()
        with patch.object(v, "get_vector_store", new=AsyncMock(side_effect=AssertionError("Should not initialize"))):
            stats = await v.run_vectorize_async()
        self.assertEqual(stats["vectorized"], 0)
        self.assertEqual(stats["skipped"], 2)

    async def test_new_product_only(self):
        await v.run_vectorize_async()
        db.upsert_products(pd.DataFrame([dict(source="TIKI", product_id="002", product_name="New tea")]))
        with patch.object(self.store.embeddings, "embed_documents", wraps=self.store.embeddings.embed_documents) as embed:
            stats = await v.run_vectorize_async()
        self.assertEqual(stats["vectorized"], 1)
        self.assertEqual(stats["skipped"], 2)
        self.assertEqual(embed.call_count, 1)

    async def test_missing_chunk_is_repaired(self):
        await v.run_vectorize_async()
        self.conn.execute(f"DELETE FROM {v.VECTOR_TABLE} WHERE id = (SELECT id FROM {v.VECTOR_TABLE} WHERE json_extract_string(metadata, '$.source') = 'TIKI' LIMIT 1)")
        stats = await v.run_vectorize_async()
        self.assertEqual(stats["vectorized"], 1)
        self.assertEqual(stats["skipped"], 1)

    async def test_force_regenerates(self):
        await v.run_vectorize_async()
        stats = await v.run_vectorize_async(force=True)
        self.assertEqual(stats["vectorized"], 2)
        self.assertEqual(stats["skipped"], 0)

    async def test_filtered_retrieval_ignores_duplicate_chunk_crowding(self):
        from src import search
        await v.run_vectorize_async()
        self.conn.execute(f"""INSERT INTO {v.VECTOR_TABLE}
            SELECT 'duplicate_' || i::VARCHAR, v.text, v.embedding, v.metadata
            FROM {v.VECTOR_TABLE} v CROSS JOIN range(100) t(i)
            WHERE json_extract_string(v.metadata, '$.source') = 'TIKI'
            AND json_extract_string(v.metadata, '$.chunk_index') = '0'
        """)
        with patch.object(search, "get_vector_store", new=AsyncMock(return_value=self.store)):
            docs = await search._retrieve_documents("tea", {("OTHER", "001"): {}}, 50)
            all_docs = await search._retrieve_documents("tea", {("OTHER", "001"): {}, ("TIKI", "001"): {}}, 50)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].metadata["source"], "OTHER")
        self.assertEqual(len(all_docs), 2)

    async def test_failed_update_retries_next_run(self):
        await v.run_vectorize_async()
        db.upsert_products(pd.DataFrame([dict(source="TIKI", product_id="001", description="Updated")]))
        with patch.object(self.store.embeddings, "embed_documents", side_effect=RuntimeError("API failed")):
            with self.assertRaises(RuntimeError):
                await v.run_vectorize_async()
        stats = await v.run_vectorize_async()
        self.assertEqual(stats["vectorized"], 1)
        self.assertEqual(stats["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
