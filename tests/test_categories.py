import unittest
from unittest.mock import patch

import duckdb

from data import database
from data.categories import CATEGORY_MAPPING, canonical_category, product_category


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

    def test_buudien_fallback_is_conservative(self):
        self.assertEqual(product_category('Đặc sản miền Bắc', 'Nước mắm Phú Quốc', '', 'BUUDIEN'), 'Gia vị và chế biến')
        self.assertEqual(product_category('', 'Trà sen', '', 'BUUDIEN'), 'Đồ uống')
        self.assertEqual(product_category('', 'Đặc sản địa phương', 'Sản phẩm là nước mắm truyền thống.', 'BUUDIEN'), 'Gia vị và chế biến')
        self.assertEqual(product_category('', 'Đặc sản địa phương', 'Dùng cùng nước mắm.', 'BUUDIEN'), 'Chưa phân loại')
        self.assertEqual(product_category('', 'Bánh trà xanh', '', 'BUUDIEN'), 'Chưa phân loại')
        self.assertEqual(product_category('', 'Nước mắm', '', 'TIKTOK'), 'Chưa phân loại')
        self.assertEqual(product_category('Trái cây', 'Trà sen', '', 'BUUDIEN'), 'Trái cây')

    def test_read_infers_without_changing_stored_category(self):
        from contextlib import nullcontext
        with duckdb.connect(':memory:') as connection:
            database.initialize_products(connection)
            connection.execute("INSERT INTO products (source, product_id, product_name, category_name) VALUES ('BUUDIEN', '2', 'Trà sen', 'Đặc sản miền Bắc')")
            with patch.object(database, 'connect', return_value=nullcontext(connection)):
                products = database.read_products()
            self.assertEqual(products.iloc[0]['category_name'], 'Đồ uống')
            self.assertEqual(connection.execute('SELECT category_name FROM products').fetchone()[0], 'Đặc sản miền Bắc')
