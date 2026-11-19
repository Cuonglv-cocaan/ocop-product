import unittest
from contextlib import nullcontext
from unittest.mock import patch

import duckdb

from data import database
from data.product_metadata import buudien_province, buudien_stars, canonical_province


class ProductMetadataTests(unittest.TestCase):
    def test_provinces_preserve_known_and_use_unambiguous_hints(self):
        self.assertEqual(buudien_province('Hà Nội', 'Trà Huế', ''), 'Hà Nội')
        self.assertEqual(buudien_province('Thừa Thiên Huế', '', ''), 'Huế')
        self.assertEqual(buudien_province('', 'Tỏi Lý Sơn', ''), 'Quảng Ngãi')
        self.assertEqual(buudien_province('', 'Đặc sản', 'Xuất xứ: Hà Giang.'), 'Hà Giang')
        self.assertEqual(buudien_province('', 'Trà Hà Nội Huế', 'Xuất xứ: Hà Nội.'), 'Chưa cập nhật')
        self.assertEqual(buudien_province('', 'Đặc sản', 'Giao hàng đến Hà Nội.'), 'Chưa cập nhật')

    def test_stars_require_explicit_unambiguous_ocop(self):
        self.assertEqual(buudien_stars('', 'Trà OCOP 4 sao', ''), '4')
        self.assertEqual(buudien_stars('', 'Trà', 'Đạt 3 sao OCOP.'), '3')
        self.assertEqual(buudien_stars('', 'Trà 5 sao', ''), '')
        self.assertEqual(buudien_stars('', 'Chưa đạt OCOP 4 sao', ''), '')
        self.assertEqual(buudien_stars('', 'OCOP 3 sao', 'OCOP 4 sao'), '')
        self.assertEqual(buudien_stars('3', 'OCOP 4 sao', ''), '3')

    def test_province_variants_and_invalid_localities(self):
        for value, expected in [('Tỉnh Cao Bằng', 'Cao Bằng'), ('TP. Hà Nội', 'Hà Nội'),
                                ('TP. Huế', 'Huế'), ('Thanh Hoá', 'Thanh Hóa')]:
            with self.subTest(value=value):
                self.assertEqual(canonical_province(value), expected)
        for value in ('Số 8', 'Nghĩa Trung', 'Hưng Lộc', 'Mỏ Cày', 'Sen Thủy'):
            with self.subTest(value=value):
                self.assertEqual(buudien_province(value, 'Sản phẩm', ''), 'Chưa cập nhật')
        self.assertEqual(buudien_province('Số 8', 'Trà Hà Giang', ''), 'Hà Giang')

    def test_enrichment_applies_on_read_without_modifying_storage(self):
        with duckdb.connect(':memory:') as connection:
            database.initialize_products(connection)
            connection.execute("INSERT INTO products (source, product_id, product_name, province_name, ocop_stars) VALUES ('BUUDIEN', '1', 'Trà Huế OCOP 4 sao', '', '')")
            with patch.object(database, 'connect', return_value=nullcontext(connection)):
                row = database.read_products().iloc[0]
            self.assertEqual((row['province_name'], row['ocop_stars']), ('Huế', '4'))
            self.assertEqual(connection.execute('SELECT province_name, ocop_stars FROM products').fetchone(), ('', ''))


if __name__ == '__main__':
    unittest.main()
