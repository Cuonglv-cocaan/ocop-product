import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crawlers.tiki import crawl_tiki as tiki
from crawlers.tiktok import crawl_tiktok as tiktok


class CrawlerTests(unittest.TestCase):
    def test_province_rules_are_shared_and_known_values_are_preserved(self):
        for title in ['Tỏi Lý Sơn', 'Đặc sản Phan Thiết', 'Cà phê Dak Lak',
                      'Trà Hà Nội và Huế', 'Mắm Lê Gia']:
            with self.subTest(title=title):
                expected = tiki.infer_province_hint(title)['province_hint'] or 'Chưa cập nhật'
                self.assertEqual(tiktok.normalize_ocop(dict(product_name=title))['province_name'], expected)
        self.assertEqual(tiktok.province_name(dict(product_name='Tỏi Lý Sơn', province_name='Hà Nội')), 'Hà Nội')

    def test_province_backfill_is_repeatable_and_preserves_other_cells(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / 'products_tiktok.csv'
            rows = [dict(source='TIKTOK', product_name='Tỏi Lý Sơn', province_name='Chưa cập nhật', extra='001'),
                    dict(source='TIKTOK', product_name='Trà Huế', province_name='Hà Nội', extra='002'),
                    dict(source='TIKTOK', product_name='Trà Huế Hà Nội', province_name='', extra='003')]
            with path.open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            self.assertEqual(tiktok.backfill_provinces(folder), 1)
            with path.open(encoding='utf-8-sig', newline='') as stream:
                updated = list(csv.DictReader(stream))
            self.assertEqual(updated, [{**rows[0], 'province_name': 'Quảng Ngãi'}, *rows[1:]])
            before = path.read_bytes()
            self.assertEqual(tiktok.backfill_provinces(folder), 0)
            self.assertEqual(path.read_bytes(), before)

    def test_tiki_url_file_supports_bom_comments_and_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'urls_tiki.txt'
            path.write_text('# links\nhttps://tiki.vn/tea-p001.html\n\nhttps://tiki.vn/tea-p001.html\n', encoding='utf-8-sig')
            with patch.object(tiki, 'URL_FILE', path):
                self.assertEqual(tiki.load_urls(), ['https://tiki.vn/tea-p001.html'])

    def test_tiktok_malformed_optional_metadata_does_not_drop_product(self):
        product = {'@type': 'Product', 'name': 'Tea OCOP 4 sao', 'offers': 'invalid', 'aggregateRating': 'invalid'}
        html = '<script type="application/ld+json">' + json.dumps(product) + '</script>'
        row = tiktok.parse_html(html, tiktok.DEFAULT_URL)
        self.assertEqual(row['product_name'], 'Tea OCOP 4 sao')
        self.assertEqual(row['price'], '')
        self.assertEqual(row['crawl_status'], 'partial')

    def test_tiktok_partial_update_preserves_existing_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            tiktok.upsert(folder, dict(source='TIKTOK', product_id='001', product_name='Tea',
                                      price=120000, currency='VND', description='Known', province_name='Hà Nội'))
            tiktok.upsert(folder, dict(source='TIKTOK', product_id='001', product_name='Tea'))
            rows = tiktok.read_output_rows(folder)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['price'], '120000')
            self.assertEqual(rows[0]['province_name'], 'Hà Nội')
            self.assertEqual(rows[0]['description'], 'Known')


if __name__ == '__main__':
    unittest.main()
