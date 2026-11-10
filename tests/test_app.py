import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from data.database import COLUMNS


class AppTests(unittest.TestCase):
    def test_missing_prices_and_invalid_stars_render_and_navigate(self):
        rows = []
        for index, (price, stars) in enumerate([('', ''), ('inf', 'inf'), ('-5', '4.5'), ('0', '4')]):
            row = dict.fromkeys(COLUMNS, '')
            row.update(source='TIKTOK', product_id=str(index), product_name=f'Tea {index}',
                       price=price, ocop_stars=stars)
            rows.append(row)
        with patch('data.database.read_products', return_value=pd.DataFrame(rows)):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/app.py')).run(timeout=20)
            self.assertFalse(app.exception)
            content = '\n'.join(m.value for m in app.markdown)
            self.assertIn('Giá chưa cập nhật', content)
            self.assertIn('OCOP chưa cập nhật', content)
            self.assertIn('0 ₫', content)
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['page'], 'Sản phẩm OCOP')


if __name__ == '__main__':
    unittest.main()
