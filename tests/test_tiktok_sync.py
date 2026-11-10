import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb

from crawlers.tiktok.crawl_tiktok import OCOP_FIELDS, sync_master


class TikTokSyncTests(unittest.TestCase):
    def test_sync_preserves_ids_and_other_sources_on_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            database = folder / 'products.duckdb'
            with (folder / 'products_tiktok.csv').open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=OCOP_FIELDS)
                writer.writeheader()
                writer.writerow(dict(product_id='001', product_name='Tea', source='TIKTOK', price='120000'))
            with patch.dict(os.environ, {'DUCKDB_PATH': str(database), 'DUCKDB_READ_ONLY': 'false'}):
                sync_master(folder)
                with duckdb.connect(str(database)) as conn:
                    conn.execute("INSERT INTO products (source, product_id, product_name) VALUES ('TIKI', '001', 'Coffee')")
                sync_master(folder)
            with duckdb.connect(str(database)) as conn:
                self.assertEqual(conn.execute(
                    'SELECT source, product_id, product_name FROM products ORDER BY source'
                ).fetchall(), [('TIKI', '001', 'Coffee'), ('TIKTOK', '001', 'Tea')])

    def test_no_output_does_not_start_pipeline(self):
        with tempfile.TemporaryDirectory() as directory, patch('subprocess.run') as run:
            sync_master(Path(directory))
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
