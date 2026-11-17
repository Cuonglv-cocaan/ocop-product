import unittest
from decimal import Decimal
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class NumericFormTests(unittest.TestCase):
    def setUp(self):
        import streamlit as st
        st.cache_data.clear()

    def test_request_edit_keeps_scaled_decimal_amount(self):
        source = '''from decimal import Decimal
from src.purchase_ui import request_form
request_form(dict(id=1, quantity=Decimal('100.000'), budget=Decimal('1000.50')))
'''
        with patch('data.suppliers.catalog_items', return_value=[]), \
                patch('data.purchase.edit_request') as save, patch('src.purchase_ui._done'):
            app = AppTest.from_string(source).run()
            self.assertFalse(app.exception)
            self.assertEqual(next(w for w in app.text_input if w.label == 'Số lượng *').value, '100')
            self.assertEqual(next(w for w in app.text_input if w.label.startswith('Ngân sách')).value, '1.000,5')
            next(b for b in app.button if b.label == 'Lưu thay đổi nhu cầu').click().run()
            self.assertFalse(app.exception)
            fields = save.call_args.args[2]
            self.assertEqual(fields['quantity'], Decimal('100'))
            self.assertEqual(fields['budget'], Decimal('1000.5'))

    def test_request_creation_parses_grouping_and_keeps_optional_budget_empty(self):
        with patch('data.suppliers.catalog_items', return_value=[]), \
                patch('data.purchase.create_request', return_value=1) as save, patch('src.purchase_ui._done'):
            app = AppTest.from_string('from src.purchase_ui import request_form\nrequest_form()').run()
            next(w for w in app.text_input if w.label == 'Số lượng *').set_value('1.000,5')
            next(b for b in app.button if b.label == 'Tạo phiếu nhu cầu').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(save.call_args.args[1]['quantity'], Decimal('1000.5'))
            self.assertIsNone(save.call_args.args[1]['budget'])

    def test_supplier_minimum_and_reference_price_are_decimals(self):
        source = "from src.supplier_ui import _products\n_products(None, {'id': 1, 'status': 'approved'}, {'role': 'seller'})"
        with patch('data.suppliers.list_products', return_value=[]), \
                patch('data.suppliers.catalog_items', return_value=[dict(source='TIKI', product_id='1', product_name='Tea')]), \
                patch('data.suppliers.save_product') as save, patch('src.supplier_ui._success'):
            app = AppTest.from_string(source).run()
            next(w for w in app.text_input if w.label.startswith('Số lượng đặt tối thiểu')).set_value('1.000,5')
            next(w for w in app.text_input if w.label.startswith('Giá tham khảo tự khai báo')).set_value('1.000.000')
            next(b for b in app.button if b.label == 'Lưu cung ứng').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(save.call_args.kwargs['minimum_order'], Decimal('1000.5'))
            self.assertEqual(save.call_args.kwargs['structured']['reference_price'], Decimal('1000000'))
            self.assertEqual(save.call_args.kwargs['structured']['service_regions'], [])
            self.assertEqual(save.call_args.kwargs['structured']['preparation_days'], '')

    def test_supplier_selectors_preserve_legacy_values_and_payload_types(self):
        link = dict(source='TIKI', product_id='1', product_name='Tea', is_active=True,
                    minimum_order=Decimal('100.000'), unit='kiện cũ', category='Danh mục cũ',
                    preparation_time='Theo lịch sản xuất', capacity_description='Theo mùa',
                    service_regions=['Tỉnh lịch sử', 'Hà Nội'], preparation_days=3,
                    reference_price=Decimal('1000.50'), reference_price_unit='kiện cũ')
        source = "from src.supplier_ui import _products\n_products(None, {'id': 1, 'status': 'approved'}, {'role': 'seller'})"
        with patch('data.suppliers.list_products', return_value=[link]), \
                patch('data.suppliers.catalog_items', return_value=[]), \
                patch('data.suppliers.save_product') as save, patch('src.supplier_ui._success'):
            app = AppTest.from_string(source).run()
            self.assertFalse(app.exception)
            self.assertEqual([s.value for s in app.subheader],
                             ['Điều kiện đặt hàng', 'Khu vực và thời gian', 'Giá tham khảo'])
            unit = next(w for w in app.selectbox if w.label == 'Đơn vị tính')
            category = next(w for w in app.selectbox if w.label == 'Danh mục cung ứng khai báo')
            self.assertEqual(unit.value, 'kiện cũ')
            self.assertIn('kg', unit.options)
            self.assertEqual(category.value, 'Danh mục cũ')
            self.assertEqual(app.multiselect[0].value, ['Tỉnh lịch sử', 'Hà Nội'])
            self.assertEqual(app.number_input[0].value, 3)
            app.number_input[0].set_value(0)
            next(b for b in app.button if b.label == 'Lưu cung ứng').click().run()
            self.assertFalse(app.exception)
            args = save.call_args.kwargs
            self.assertEqual(args['minimum_order'], Decimal('100'))
            self.assertEqual(args['unit'], 'kiện cũ')
            self.assertEqual(args['structured'], dict(category='Danh mục cũ',
                service_regions=['Tỉnh lịch sử', 'Hà Nội'], preparation_days='0',
                reference_price=Decimal('1000.50'), reference_price_unit='kiện cũ'))
