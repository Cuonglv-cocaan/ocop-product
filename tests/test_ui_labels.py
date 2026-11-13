import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from src.ui_labels import number_label, money_label, date_label, time_label, field_line, status_label


class DisplayFormatTests(unittest.TestCase):
    def test_decimal_scale_is_not_a_thousands_separator(self):
        self.assertEqual(number_label(Decimal('100.000')), '100')
        self.assertEqual(number_label(Decimal('100000.000')), '100.000')
        self.assertEqual(number_label(Decimal('100.125')), '100,125')
        self.assertEqual(number_label(Decimal('0.0005')), '0,0005')
        self.assertEqual(money_label(Decimal('450000.00')), '450.000 ₫')
        self.assertEqual(money_label(0), '0 ₫')

    def test_dates_and_known_timezones(self):
        self.assertEqual(date_label('2026-11-20'), '20/11/2026')
        self.assertEqual(time_label(datetime(2026, 11, 19, 18, 30, tzinfo=timezone.utc)),
                         '20/11/2026 01:30')

    def test_unknown_timezone_is_never_assumed(self):
        self.assertEqual(time_label(datetime(2026, 11, 20, 10, 30)),
                         '20/11/2026 10:30 (chưa xác định múi giờ)')

    def test_missing_values_are_not_invented(self):
        for formatter in (number_label, money_label, date_label, time_label):
            self.assertEqual(formatter(None), 'Chưa cập nhật')
            self.assertEqual(formatter(''), 'Chưa cập nhật')

    def test_html_escapes_user_content(self):
        with patch('src.ui_labels.st.markdown') as render:
            field_line(('Tên', '<script>alert(1)</script>'))
            self.assertIn('&lt;script&gt;', render.call_args.args[0])
            self.assertNotIn('<script>', render.call_args.args[0])
            status_label('selected', '<img src=x onerror=alert(1)>')
            self.assertIn('&lt;img', render.call_args.args[0])
