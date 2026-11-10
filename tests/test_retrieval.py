import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from data import database as db
from src import search


class RetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_sql_filters_before_ranking_and_deduplicates_chunks(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(db, 'DUCKDB_PATH', Path(directory) / 'test.duckdb'):
            with db.connect() as conn:
                conn.execute('CREATE TABLE ocop_embeddings_gemini (text VARCHAR, metadata VARCHAR, embedding FLOAT[])')
                for source, pid, vector in [('TIKI', '001', [1., 0.]), ('TIKI', '001', [.9, .1]),
                                            ('TIKTOK', '001', [0., 1.]), ('TIKI', 'excluded', [1., 0.])]:
                    conn.execute('INSERT INTO ocop_embeddings_gemini VALUES (?, ?, ?)',
                                 [pid, json.dumps(dict(source=source, product_id=pid)), vector])
            embeddings = SimpleNamespace(embed_query=Mock(return_value=[1., 0.]))
            with patch.object(search, 'get_vector_store', new=AsyncMock(return_value=SimpleNamespace(embeddings=embeddings))):
                docs = await search._retrieve_documents('tea', {('TIKI', '001'): {}, ('TIKTOK', '001'): {}}, 5)
            self.assertEqual([(doc.metadata['source'], doc.metadata['product_id']) for doc in docs],
                             [('TIKI', '001'), ('TIKTOK', '001')])


if __name__ == '__main__':
    unittest.main()
