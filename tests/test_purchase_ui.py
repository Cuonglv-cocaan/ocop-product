import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest
from data import purchase
from data.database import COLUMNS


class PurchaseUITests(unittest.TestCase):
    def detail(self):
        now = datetime.now(purchase.ZONE)
        row = dict(id=1, title='Test demand', category='Tea', description='Test description', quantity='10',
                   unit='box', budget=None, budget_type='total', delivery_location='Test province',
                   delivery_deadline=purchase.today() + timedelta(days=7), additional_requirements='',
                   source=None, product_id=None, status='quoted', created_at=now, selected_quote_id=None)
        match = dict(id=1, supplier_id=1, supplier_name='Unit A', status='quoted', assigned_at=now, decline_reason='')
        quote = dict(id=1, match_id=1, supplier_name='Unit A', version=1, quantity='10', unit='box',
                     unit_price='100.00', shipping_fee=None, total_amount='1000.00', expected_delivery=row['delivery_deadline'],
                     valid_until=now + timedelta(days=1), status='active', excluded_costs='Shipping not included', notes='Test')
        return dict(request=row, matches=[match], quotes=[quote], contacts=None, events=[])

    def app(self, role='buyer'):
        product = dict.fromkeys(COLUMNS, '')
        product.update(source='TIKI', product_id='001', product_name='Tea')
        for mock in (patch('data.database.read_products', return_value=pd.DataFrame([product])),
                     patch('data.auth.current_user', return_value={'id': 1, 'username': 'demo', 'role': role}),
                     patch('data.suppliers.catalog_items', return_value=[{'source': 'TIKI', 'product_id': '001', 'product_name': 'Tea'}])):
            mock.start()
            self.addCleanup(mock.stop)
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/app.py'))
        app.session_state['page'] = 'Nhu cầu'
        app.session_state['auth_session'] = object()
        return app

    def test_catalog_reference_prefill_create_and_no_owner_field(self):
        with patch('data.purchase.list_requests', return_value=[]), \
                patch('data.purchase.create_request', return_value=9) as create:
            app = self.app()
            app.session_state['purchase_reference'] = dict(source='TIKI', product_id='001', title='Tea', category='Tea category')
            app.run(timeout=20)
            self.assertFalse(app.exception)
            self.assertEqual(next(w for w in app.text_input if w.label == 'Tiêu đề *').value, 'Tea')
            for label, value in [('Số lượng *', '10'), ('Đơn vị tính *', 'box'),
                                 ('Địa điểm giao *', 'Test province'), ('Email liên hệ riêng', 'demo@example.com')]:
                next(w for w in app.text_input if w.label == label).set_value(value)
            next(w for w in app.text_area if w.label == 'Mô tả nhu cầu *').set_value('Test request')
            next(b for b in app.button if b.label == 'Tạo phiếu nhu cầu').click().run()
            self.assertFalse(app.exception)
            fields = create.call_args.args[1]
            self.assertEqual((fields['source'], fields['product_id']), ('TIKI', '001'))
            self.assertNotIn('buyer_id', fields)
            self.assertTrue(app.success)
            self.assertNotIn('purchase_reference', app.session_state)

    def test_guest_login_preserves_only_public_catalog_reference(self):
        import secrets
        with patch('data.database.read_products', return_value=pd.DataFrame([dict.fromkeys(COLUMNS, '')])), \
                patch('data.auth.authenticate', return_value=object()), \
                patch('data.auth.current_user', return_value={'id': 1, 'username': 'buyer01', 'role': 'buyer'}), \
                patch('data.suppliers.catalog_items', return_value=[]), \
                patch('data.purchase.list_requests', return_value=[]):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/app.py'))
            app.session_state['page'] = 'Nhu cầu'
            app.session_state['purchase_reference'] = {'source': 'TIKI', 'product_id': '001', 'title': 'Tea', 'category': 'Tea', 'contact_phone': 'private'}
            app.session_state['private_note'] = 'Private draft'
            app.run(timeout=20)
            app.text_input(key='login_username').set_value('buyer01')
            app.text_input(key='login_password').set_value(secrets.token_urlsafe(16))
            next(b for b in app.button if b.label == 'Đăng nhập').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['page'], 'Nhu cầu')
            self.assertNotIn('private_note', app.session_state)
            self.assertNotIn('contact_phone', app.session_state['purchase_reference'])

    def test_buyer_compares_and_selects_quote(self):
        detail = self.detail()
        with patch('data.purchase.list_requests', return_value=[detail['request']]), \
                patch('data.purchase.request_detail', return_value=detail), \
                patch('data.purchase.select_quote') as select:
            app = self.app().run(timeout=20)
            self.assertFalse(app.exception)
            next(w for w in app.checkbox if 'Tôi hiểu' in w.label).check()
            next(b for b in app.button if b.label == 'Chọn phương án').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(select.call_args.args[1:], (1, 1))
            self.assertTrue(app.success)

    def test_seller_quote_form_sends_strings_without_client_total(self):
        detail = self.detail()
        with patch('data.purchase.list_requests', return_value=[detail['request']]), \
                patch('data.purchase.request_detail', return_value=detail), \
                patch('data.purchase.submit_quote', return_value=2) as submit:
            app = self.app('seller').run(timeout=20)
            self.assertFalse(app.exception)
            next(w for w in app.text_input if w.label == 'Đơn giá VND').set_value('100.00')
            next(w for w in app.text_area if w.label.startswith('Chi phí chưa bao gồm')).set_value('Shipping not included')
            next(b for b in app.button if b.label == 'Gửi phiên bản báo giá mới').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(submit.call_args.kwargs['unit_price'], '100.00')
            self.assertNotIn('total_amount', submit.call_args.kwargs)
            self.assertTrue(app.success)

    def test_admin_assigns_approved_unit_manually(self):
        detail = self.detail()
        with patch('data.purchase.list_requests', return_value=[detail['request']]), \
                patch('data.purchase.request_detail', return_value=detail), \
                patch('data.suppliers.list_suppliers', return_value=[dict(id=2, name='Unit B', status='approved')]), \
                patch('data.purchase.assign_supplier', return_value=2) as assign:
            app = self.app('admin').run(timeout=20)
            self.assertFalse(app.exception)
            next(b for b in app.button if b.label == 'Phân nhà cung cấp').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(assign.call_args.args[1:], (1, 2))
            self.assertTrue(app.success)
