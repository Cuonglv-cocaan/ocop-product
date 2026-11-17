import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from src.ui_labels import number_label, money_label, date_label, time_label, field_line, status_label
from src.ui_labels import parse_vn_number, render_stepper, STATES


class DisplayFormatTests(unittest.TestCase):
    def test_stepper_marks_passed_and_current_steps(self):
        for index, status in enumerate(('open', 'assigned', 'quoted', 'selected', 'connected')):
            with self.subTest(status=status), patch('src.ui_labels.st.markdown') as render:
                render_stepper(status)
                markup = render.call_args.args[0]
                self.assertEqual(markup.count('class="ocop-step done"'), index)
                self.assertEqual(markup.count('>✓</span>'), index)
                self.assertEqual(markup.count('aria-current="step"'), 1)
                self.assertIn(f'title="{STATES[status]}"', markup)

    def test_terminal_status_uses_badge_instead_of_stepper(self):
        for status in ('cancelled', 'closed_no_match'):
            with self.subTest(status=status), patch('src.ui_labels.st.markdown') as render:
                render_stepper(status)
                markup = render.call_args.args[0]
                self.assertIn(STATES[status], markup)
                self.assertNotIn('ocop-stepper', markup)
    def test_parse_vietnamese_and_plain_decimal_numbers(self):
        examples = {
            '1.000.000': '1000000', '1000000': '1000000',
            '1.000,5': '1000.5', '1000.5': '1000.5',
            '1.000': '1000', '100,125': '100.125', '0.125': '0.125',
            '0,0005': '0.0005', '  -1.234,50  ': '-1234.50',
            '+1.000.000,25': '1000000.25', '0': '0', '1,000': '1',
        }
        for text, expected in examples.items():
            with self.subTest(text=text):
                result = parse_vn_number(text)
                self.assertIsInstance(result, Decimal)
                self.assertEqual(result, Decimal(expected))

    def test_parse_rejects_invalid_numbers_with_vietnamese_errors(self):
        for text in ('', '  ', None, 'NaN', 'Infinity', '-inf', '1e6', 'abc',
                     '1.00.000', '1,000,000', '1,000.5', '1.000,', '.5',
                     '1 000', '1000đ', '1_000', '--1', True, 1000):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'nhập|định dạng|văn bản'):
                parse_vn_number(text)

    def test_displayed_database_values_can_be_edited_without_changing_amount(self):
        for value in ('100.000', '100.125', '1000000.50', '0.0005', '-1234.50', '0'):
            with self.subTest(value=value):
                amount = Decimal(value)
                self.assertEqual(parse_vn_number(number_label(amount)), amount)

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
