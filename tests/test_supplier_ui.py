import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest
from data.database import COLUMNS


class SupplierUITests(unittest.TestCase):
    def app(self, role, empty=False):
        row = dict.fromkeys(COLUMNS, '')
        row.update(source='TIKI', product_id='001', product_name='Tea')
        products = pd.DataFrame(columns=COLUMNS) if empty else pd.DataFrame([row])
        mocks = [patch('data.database.read_products', return_value=products),
                 patch('data.auth.current_user', return_value={'id': 1, 'username': 'demo', 'role': role})]
        for mock in mocks:
            mock.start()
            self.addCleanup(mock.stop)
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/app.py'))
        app.session_state['auth_session'] = object()
        app.session_state['page'] = 'Duyệt nhà cung cấp' if role == 'admin' else 'Nhà cung cấp'
        return app

    def supplier(self, status='approved'):
        return dict(id=1, name='Test unit', entity_type='', description='', province='', email='',
                    phone='', delivery_areas='', status=status, created_by=1, reviewed_by=None,
                    reviewed_at=None, rejection_reason='', is_demo=True)

    def test_buyer_registration_and_unknown_fields(self):
        with patch('data.suppliers.list_suppliers', return_value=[]), \
                patch('data.suppliers.create_application', return_value=7) as create:
            app = self.app('buyer').run(timeout=20)
            self.assertFalse(app.exception)
            next(w for w in app.text_input if w.label == 'Tên đơn vị *').set_value('My unit')
            next(b for b in app.button if b.label == 'Gửi hồ sơ đăng ký').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('#7' in result.value for result in app.success))
            fields = create.call_args.args[1]
            self.assertEqual(fields['name'], 'My unit')
            self.assertEqual(fields['province'], '')
            self.assertNotIn('status', fields)

    def test_history_available_with_empty_catalog(self):
        row = self.supplier()
        link = dict(source='TIKI', product_id='001', product_name='Sản phẩm không còn trong catalog',
                    minimum_order=None, unit='', preparation_time='', capacity_description='', is_active=True)
        with patch('data.suppliers.list_suppliers', return_value=[row]), \
                patch('data.suppliers.get_supplier', return_value=row), \
                patch('data.suppliers.list_products', return_value=[link]), \
                patch('data.suppliers.catalog_items', return_value=[]):
            app = self.app('seller', empty=True).run(timeout=20)
            self.assertFalse(app.exception)
            content = '\n'.join(w.value for w in app.markdown)
            self.assertIn('Sản phẩm không còn trong catalog', content)
            self.assertIn('Chưa cập nhật', content)

    def test_admin_review_calls_protected_service(self):
        row = self.supplier(status='pending')
        with patch('data.suppliers.list_suppliers', return_value=[row]), \
                patch('data.suppliers.get_supplier', return_value=row), \
                patch('data.suppliers.list_products', return_value=[]), \
                patch('data.auth.require_user', return_value={'id': 1, 'role': 'admin'}), \
                patch('data.postgres.transaction') as transaction, \
                patch('data.suppliers.review_application') as review:
            app = self.app('admin').run(timeout=20)
            self.assertFalse(app.exception)
            next(b for b in app.button if b.label == 'Xác nhận quyết định').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(review.call_args.args[1:3], (1, 'approved'))
            self.assertTrue(app.success)
