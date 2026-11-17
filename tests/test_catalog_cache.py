import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import streamlit as st
from src import catalog_cache


class CatalogCacheTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        self.addCleanup(st.cache_data.clear)

    def test_catalog_cache_reuses_reads_returns_copies_and_tracks_db_and_wal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'catalog.duckdb'
            path.write_bytes(b'fake')
            with patch('data.database.DUCKDB_PATH', path), \
                    patch('data.suppliers.catalog_items', return_value=[{'product_name': 'Tea'}]) as read:
                first = catalog_cache.catalog_items()
                first[0]['product_name'] = 'Changed in one session'
                self.assertEqual(catalog_cache.catalog_items()[0]['product_name'], 'Tea')
                self.assertEqual(read.call_count, 1)
                stamp = path.stat()
                os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000))
                catalog_cache.catalog_items()
                self.assertEqual(read.call_count, 2)
                wal = Path(str(path) + '.wal')
                wal.write_bytes(b'new transaction')
                catalog_cache.catalog_items()
                self.assertEqual(read.call_count, 3)

    def test_missing_catalog_becoming_available_invalidates_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'catalog.duckdb'
            with patch('data.database.DUCKDB_PATH', path), \
                    patch('data.suppliers.catalog_items', side_effect=[[], [{'product_name': 'Tea'}]]) as read:
                self.assertEqual(catalog_cache.catalog_items(), [])
                path.write_bytes(b'fake')
                self.assertEqual(catalog_cache.catalog_items()[0]['product_name'], 'Tea')
                self.assertEqual(read.call_count, 2)
