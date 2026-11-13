import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest
from data import purchase
from data.database import COLUMNS


class PurchaseUITests(unittest.TestCase):
    def test_buyer_list_or_empty_state_prioritizes_create_button_not_form(self):
        detail = self.detail()
        for rows in ([], [detail['request']]):
            with self.subTest(has_requests=bool(rows)), \
                    patch('data.purchase.list_requests', return_value=rows), \
                    patch('data.purchase.request_detail', return_value=detail):
                app = self.app().run(timeout=20)
                self.assertFalse(app.exception)
                self.assertFalse(any(w.label == 'Tiêu đề *' for w in app.text_input))
                self.assertTrue(any(b.label == 'Tạo nhu cầu' for b in app.button))
                if not rows:
                    self.assertTrue(any('Bạn chưa có nhu cầu mua hàng' in i.value for i in app.info))
                next(b for b in app.button if b.label == 'Tạo nhu cầu').click().run()
                self.assertFalse(app.exception)
                self.assertTrue(any(w.label == 'Tiêu đề *' for w in app.text_input))
                self.assertFalse(app.dataframe)
                self.assertFalse(any(e.label == 'Yêu cầu trước đây' for e in app.expander))
                next(b for b in app.button if b.label == 'Quay lại danh sách').click().run()
                self.assertFalse(app.exception)
                self.assertFalse(any(w.label == 'Tiêu đề *' for w in app.text_input))
                self.assertTrue(any(b.label == 'Tạo nhu cầu' for b in app.button))

    def test_buyer_creation_error_keeps_form_and_draft_visible(self):
        with patch('data.purchase.list_requests', return_value=[]), \
                patch('data.purchase.create_request', side_effect=ValueError('Thiếu thông tin')):
            app = self.app().run(timeout=20)
            next(b for b in app.button if b.label == 'Tạo nhu cầu').click().run()
            next(w for w in app.text_input if w.label == 'Tiêu đề *').set_value('Draft request')
            next(b for b in app.button if b.label == 'Tạo phiếu nhu cầu').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.error)
            self.assertTrue(app.session_state['_buyer_create_open'])
            self.assertEqual(next(w for w in app.text_input if w.label == 'Tiêu đề *').value, 'Draft request')

    def test_table_and_detail_agree_on_scaled_decimal_quantity(self):
        from decimal import Decimal
        detail = self.detail()
        detail['request']['quantity'] = Decimal('100.000')
        detail['request']['unit'] = 'gói'
        with patch('data.purchase.list_requests', return_value=[detail['request']]), \
                patch('data.purchase.request_detail', return_value=detail):
            app = self.app('seller').run(timeout=20)
            self.assertFalse(app.exception)
            self.assertEqual(app.dataframe[0].value.iloc[0]['Số lượng'], '100')
            self.assertEqual(app.dataframe[0].value.iloc[0]['Hạn giao'], detail['request']['delivery_deadline'].strftime('%d/%m/%Y'))
            self.assertTrue(any(m.label == 'Số lượng cần mua' and m.value == '100 gói' for m in app.metric))

    def test_seller_kpis_include_connected_and_stay_stable_after_filtering(self):
        import copy
        base = self.detail()
        rows = []
        for rid, state in enumerate(['quoted', 'selected', 'connected', 'cancelled', 'quoted'], 1):
            row = {**base['request'], 'id': rid, 'status': state}
            if rid == 5:
                row['delivery_deadline'] = purchase.today() - timedelta(days=1)
            rows.append(row)
        def detail_for(session, rid):
            detail = copy.deepcopy(base)
            detail['request'] = rows[rid - 1]
            return detail
        with patch('data.purchase.list_requests', return_value=rows), \
                patch('data.purchase.request_detail', side_effect=detail_for):
            app = self.app('seller').run(timeout=20)
            self.assertFalse(app.exception)
            self.assertEqual([(m.label, m.value) for m in app.metric][:3],
                             [('Yêu cầu được phân', '5'), ('Đang tiếp nhận báo giá', '1'), ('Đã chọn / kết nối', '2')])
            next(w for w in app.selectbox if w.label == 'Lọc yêu cầu').select('Đã chọn / kết nối').run()
            self.assertFalse(app.exception)
            self.assertEqual([m.value for m in app.metric][:3], ['5', '1', '2'])
            self.assertEqual(len(app.dataframe[0].value), 2)

    def test_seller_empty_scope_still_shows_three_zero_kpis(self):
        with patch('data.purchase.list_requests', return_value=[]):
            app = self.app('seller').run(timeout=20)
            self.assertFalse(app.exception)
            self.assertEqual([m.value for m in app.metric], ['0', '0', '0'])

    def test_buyer_cannot_choose_expired_suspended_or_past_delivery_quotes(self):
        for changes in ({'valid_until': datetime.now(purchase.ZONE) - timedelta(seconds=1)},
                        {'supplier_status': 'suspended'},
                        {'expected_delivery': purchase.today() - timedelta(days=1)}):
            with self.subTest(changes=changes):
                detail = self.detail()
                detail['quotes'][0].update(changes)
                with patch('data.purchase.list_requests', return_value=[detail['request']]), \
                        patch('data.purchase.request_detail', return_value=detail):
                    app = self.app().run(timeout=20)
                    self.assertFalse(app.exception)
                    self.assertFalse(any(b.label == 'Chọn phương án' for b in app.button))
                    self.assertTrue(any('Chưa có báo giá còn phù hợp' in info.value for info in app.info))

    def test_seller_switching_requests_does_not_reuse_quote_draft(self):
        import copy
        first = self.detail()
        second = copy.deepcopy(first)
        second['request'].update(id=2, title='Second request', quantity='20')
        second['matches'][0]['id'] = 2
        with patch('data.purchase.list_requests', return_value=[first['request'], second['request']]), \
                patch('data.purchase.request_detail', side_effect=lambda session, rid: first if rid == 1 else second):
            app = self.app('seller').run(timeout=20)
            next(w for w in app.text_input if w.label == 'Đơn giá VND').set_value('999')
            next(w for w in app.selectbox if w.label == 'Chọn yêu cầu').select(2).run()
            self.assertFalse(app.exception)
            self.assertEqual(next(w for w in app.text_input if w.label == 'Đơn giá VND').value, '')
            self.assertEqual(next(w for w in app.text_input if w.label == 'Số lượng đáp ứng').value, '20')

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
                     patch('data.leads.read_leads', return_value=[]),
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
            for label, value in [('Số lượng *', '10'),
                                 ('Địa điểm giao *', 'Test province'), ('Email liên hệ', 'demo@example.com')]:
                next(w for w in app.text_input if w.label == label).set_value(value)
            next(w for w in app.selectbox if w.label == 'Đơn vị tính *').select('hộp')
            next(w for w in app.selectbox if w.label == 'Tỉnh/thành giao hàng').select('Hà Nội')
            self.assertEqual(next(w for w in app.selectbox if w.label == 'Nhóm sản phẩm cần mua (tùy chọn)').value, 'Tea category')
            next(w for w in app.text_area if w.label == 'Mô tả nhu cầu *').set_value('Test request')
            next(b for b in app.button if b.label == 'Tạo phiếu nhu cầu').click().run()
            self.assertFalse(app.exception)
            fields = create.call_args.args[1]
            self.assertEqual((fields['source'], fields['product_id']), ('TIKI', '001'))
            self.assertNotIn('buyer_id', fields)
            self.assertEqual(fields['unit'], 'hộp')
            self.assertEqual(fields['delivery_region'], 'Hà Nội')
            self.assertEqual(fields['category'], 'Tea category')
            self.assertTrue(app.success)
            self.assertNotIn('purchase_reference', app.session_state)

    def test_guest_login_preserves_only_public_catalog_reference(self):
        import secrets
        with patch('data.database.read_products', return_value=pd.DataFrame([dict.fromkeys(COLUMNS, '')])), \
                patch('data.auth.authenticate', return_value=object()), \
                patch('data.auth.current_user', return_value={'id': 1, 'username': 'buyer01', 'role': 'buyer'}), \
                patch('data.suppliers.catalog_items', return_value=[]), \
                patch('data.leads.read_leads', return_value=[]), \
                patch('data.purchase.list_requests', return_value=[]):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/app.py'))
            app.session_state['page'] = 'Đăng nhập'
            app.session_state['purchase_reference'] = {'source': 'TIKI', 'product_id': '001', 'title': 'Tea', 'category': 'Tea', 'contact_phone': 'private'}
            app.session_state['private_note'] = 'Private draft'
            app.run(timeout=20)
            app.text_input(key='login_username').set_value('buyer01')
            app.text_input(key='login_password').set_value(secrets.token_urlsafe(16))
            next(b for b in app.button if b.label == 'Đăng nhập').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['page'], 'Nhu cầu mua hàng')
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
            self.assertEqual(app.session_state['page'], 'Yêu cầu báo giá')
            self.assertEqual([h.value for h in app.title], ['Yêu cầu báo giá'])
            self.assertTrue(any(m.label == 'Đang tiếp nhận báo giá' and m.value == '1' for m in app.metric))
            next(w for w in app.selectbox if w.label == 'Lọc yêu cầu').select('Đã kết thúc').run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Không có yêu cầu trong nhóm này' in i.value for i in app.info))
            next(w for w in app.selectbox if w.label == 'Lọc yêu cầu').select('Tất cả').run()
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
                patch('src.supplier_ui.page'), \
                patch('data.accounts.list_accounts', return_value=[]), \
                patch('data.purchase.assign_supplier', return_value=2) as assign:
            app = self.app('admin').run(timeout=20)
            self.assertFalse(app.exception)
            next(b for b in app.button if b.label == 'Phân nhà cung cấp').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(assign.call_args.args[1:], (1, 2))
            self.assertTrue(app.success)
