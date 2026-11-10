import unittest
from unittest.mock import patch

import duckdb

from data import database
from data.categories import CATEGORY_MAPPING, canonical_category


class CategoryTests(unittest.TestCase):
    def test_shared_categories_and_unmapped_values(self):
        self.assertEqual(canonical_category('Gia Vị và Chế Biến'), canonical_category(
            'Food & Beverages > Staples & Cooking Essentials > Cooking Sauces'))
        self.assertEqual(canonical_category('Đồ Ăn Vặt'), canonical_category(
            'Food & Beverages > Snacks > Dried Snacks'))
        for value in ('', None, 'New unknown category'):
            self.assertEqual(canonical_category(value), 'Chưa phân loại')
        for canonical in set(CATEGORY_MAPPING.values()):
            self.assertEqual(canonical_category(canonical), canonical)

    def test_read_maps_without_changing_stored_categories(self):
        with duckdb.connect(':memory:') as connection:
            database.initialize_products(connection)
            raw = 'Food & Beverages > Snacks > Dried Snacks'
            connection.execute("INSERT INTO products (source, product_id, category_name) VALUES ('TIKTOK', '1', ?)", [raw])
            # The reader owns its connection, so use a separate context wrapper.
            from contextlib import nullcontext
            with patch.object(database, 'connect', return_value=nullcontext(connection)):
                products = database.read_products()
            self.assertEqual(products.iloc[0]['category_name'], 'Đồ ăn vặt')
            self.assertEqual(connection.execute('SELECT category_name FROM products').fetchone()[0], raw)
