import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from data.database import COLUMNS


class AppTests(unittest.TestCase):
    def test_guest_can_submit_without_login_and_retry(self):
        from data.leads import LeadStorageError
        with patch('data.database.read_products', return_value=pd.DataFrame(columns=COLUMNS)), \
                patch('data.leads.save_guest_lead', side_effect=[ValueError('Nhập thông tin liên hệ'), LeadStorageError(), 42]) as save:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/app.py'))
            app.session_state['purchase_reference'] = {'title': 'Trà OCOP', 'source': 'TIKI', 'product_id': '001'}
            for page in ('Kết nối cung cầu', 'Nhu cầu'):
                app.session_state['page'] = page
                app.run(timeout=20)
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state['page'], 'Nhu cầu mua hàng')
                self.assertFalse(any(w.label == 'Mật khẩu' for w in app.text_input))
                self.assertIn('Trà OCOP', app.text_area[0].value)
            next(w for w in app.selectbox if w.label == 'Bạn cần hỗ trợ gì?').select('Nhờ tìm sản phẩm')
            app.text_area[0].set_value('Tìm trà làm quà')
            next(w for w in app.text_input if w.label == 'Tên liên hệ *').set_value('Khách')
            next(w for w in app.text_input if w.label == 'Email').set_value('guest@example.com')
            for _ in range(2):
                next(b for b in app.button if b.label == 'Gửi yêu cầu').click().run()
                self.assertFalse(app.exception)
                self.assertTrue(app.error)
                self.assertEqual(app.text_area[0].value, 'Tìm trà làm quà')
            next(b for b in app.button if b.label == 'Gửi yêu cầu').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('#42' in s.value for s in app.success))
            self.assertEqual(app.text_area[0].value, '')
            self.assertEqual(save.call_args.args, ('Nhờ tìm sản phẩm', 'Khách', 'guest@example.com', '', 'Tìm trà làm quà'))

    def test_guest_login_failure_success_and_logout(self):
        import secrets
        from data import auth
        row = dict.fromkeys(COLUMNS, '')
        row.update(source='TIKI', product_id='test', product_name='Test tea')
        actor = {'id': 1, 'username': 'buyer01', 'role': 'buyer'}
        session = object()
        password = secrets.token_urlsafe(18)
        with patch('data.database.read_products', return_value=pd.DataFrame([row])), \
                patch('data.auth.authenticate', side_effect=[auth.AccessDenied('Đăng nhập không đúng'), session]) as login, \
                patch('data.auth.current_user', return_value=actor):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/app.py'))
            app.session_state['page'] = 'Đăng nhập'
            app.run(timeout=20)
            self.assertFalse(app.exception)
            self.assertEqual(len(app.text_area), 0)
            app.text_input(key='login_username').set_value('buyer01')
            app.text_input(key='login_password').set_value(password)
            app.button[0].click().run()
            self.assertTrue(app.error)
            self.assertNotIn('auth_session', app.session_state)
            app.text_input(key='login_username').set_value('buyer01')
            app.text_input(key='login_password').set_value(password)
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertIs(app.session_state['auth_session'], session)
            self.assertEqual(login.call_count, 2)
            app.session_state['private_note'] = 'Private draft'
            app.button(key='logout').click().run()
            self.assertFalse(app.exception)
            self.assertNotIn('auth_session', app.session_state)
            self.assertNotIn('private_note', app.session_state)

    def test_buyer_uses_one_purchase_page_and_can_read_legacy_requests(self):
        row = dict.fromkeys(COLUMNS, '')
        row.update(source='TIKI', product_id='test', product_name='Test tea')
        actor = {'id': 1, 'username': 'buyer01', 'role': 'buyer'}
        with patch('data.database.read_products', return_value=pd.DataFrame([row])), \
                patch('data.auth.current_user', return_value=actor), \
                patch('data.suppliers.catalog_items', return_value=[]), \
                patch('data.purchase.list_requests', return_value=[]), \
                patch('data.leads.read_leads', return_value=[dict(id=42, note='Old request')]), \
                patch('data.leads.update_note') as update:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/app.py'))
            app.session_state['auth_session'] = object()
            for old_page in ('Kết nối cung cầu', 'Yêu cầu của tôi', 'Nhu cầu'):
                app.session_state['page'] = old_page
                app.run(timeout=20)
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state['page'], 'Nhu cầu mua hàng')
                self.assertEqual([h.value for h in app.title], ['Nhu cầu mua hàng'])
                self.assertTrue(any(s.value == 'Nhu cầu đã gửi' for s in app.header))
                self.assertTrue(any(e.label == 'Yêu cầu trước đây' for e in app.expander))
                self.assertFalse(any(b.label == 'Gửi yêu cầu' for b in app.button))
            app.text_area(key='private_note').set_value('Updated old request')
            next(b for b in app.button if b.label == 'Lưu nội dung').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(update.call_args.args[1:], (42, 'Updated old request'))

    def test_directory_refreshes_cached_discovery_without_key_prefix(self):
        row = dict.fromkeys(COLUMNS, '')
        row.update(source='TIKI', product_id='1', product_name='Tea')
        def legacy_discovery():
            pass
        with patch('data.database.read_products', return_value=pd.DataFrame([row])), \
                patch('src.search.product_discovery', new=legacy_discovery):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/app.py')).run(timeout=20)
            self.assertFalse(app.exception)
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.chat_input[0].key, 'directory_discovery_question')
            self.assertTrue(any('Hiển thị 1 / 1 sản phẩm' in c.value for c in app.caption))

    def test_missing_prices_and_invalid_stars_render_and_navigate(self):
        rows = []
        for index, (price, stars) in enumerate([('', ''), ('inf', 'inf'), ('-5', '4.5'), ('0', '4')]):
            row = dict.fromkeys(COLUMNS, '')
            row.update(source='TIKTOK', product_id=str(index), product_name=f'Tea {index}',
                       price=price, ocop_stars=stars)
            rows.append(row)
        rows[-1]['source'] = 'TIKI'
        with patch('data.database.read_products', return_value=pd.DataFrame(rows)), \
                patch('src.search.search_products_async', new_callable=AsyncMock, return_value=('Không có gợi ý phù hợp', [], [])):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/app.py')).run(timeout=20)
            self.assertFalse(app.exception)
            content = '\n'.join(m.value for m in app.markdown)
            self.assertIn('Giá chưa cập nhật', content)
            self.assertIn('Chưa cập nhật', content)
            self.assertIn('0 ₫', content)
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['page'], 'Sản phẩm OCOP')
            app.selectbox(key='stars_filter').select('Chưa cập nhật').run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Hiển thị 3 / 4 sản phẩm' in c.value for c in app.caption))
            content = '\n'.join(m.value for m in app.markdown)
            self.assertNotIn('Tea 3', content)
            self.assertIn('star-chip-0', content)
            app.selectbox(key='stars_filter').select('4 sao').run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Hiển thị 1 / 4 sản phẩm' in c.value for c in app.caption))
            app.selectbox(key='source_filter').select('TIKTOK').run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Hiển thị 0 / 4 sản phẩm' in c.value for c in app.caption))
            app.selectbox(key='product_sort').select('Giá giảm dần').run()
            app.button(key='clear_filters').click().run()
            self.assertFalse(app.exception)
            for key in ('category', 'stars_filter', 'province', 'source_filter'):
                self.assertEqual(app.selectbox(key=key).value, 'Tất cả')
            self.assertEqual(app.selectbox(key='product_sort').value, 'Mặc định')
            self.assertTrue(app.button(key='clear_filters').disabled)
            self.assertTrue(any('Hiển thị 4 / 4 sản phẩm' in c.value for c in app.caption))
            app.selectbox(key='source_filter').select('TIKI').run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Hiển thị 1 / 4 sản phẩm' in c.value for c in app.caption))
            content = '\n'.join(m.value for m in app.markdown)
            self.assertIn('Tea 3', content)
            self.assertNotIn('Tea 0', content)

    def test_ai_and_directory_filters_are_independent(self):
        rows = []
        for index in range(3):
            row = dict.fromkeys(COLUMNS, '')
            row.update(source='TIKI', product_id=str(index), product_name=f'Tea {index}',
                       price='100', ocop_stars='4' if index == 0 else '')
            rows.append(row)
        with patch('data.database.read_products', return_value=pd.DataFrame(rows)), \
                patch('src.search.search_products_async', new_callable=AsyncMock) as ai:
            ai.return_value = ('Gợi ý làm quà', [{**rows[0], 'price': 100, 'ocop_stars': 4}], [])
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'src/app.py')).run(timeout=20)
            app.button[0].click().run()
            ai.assert_not_awaited()
            app.selectbox(key='stars_filter').select('Chưa cập nhật').run()
            app.chat_input(key='directory_discovery_question').set_value('quà tặng cho gia đình').run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.chat_message), 2)
            self.assertTrue(any('Hiển thị 2 / 3 sản phẩm' in c.value for c in app.caption))
            self.assertTrue(any(m.value == 'Gợi ý làm quà' for m in app.markdown))
            self.assertTrue(any(w.value == 'Tea 0' for w in app.markdown))
            self.assertEqual(set(ai.await_args.kwargs), {'history', 'top_k'})
            app.selectbox(key='product_sort').select('Giá tăng dần').run()
            ai.assert_awaited_once()
            app.button(key='clear_filters').click().run()
            self.assertEqual(len(app.session_state['directory_discovery_messages']), 2)
            ai.assert_awaited_once()
            self.assertTrue(any('Hiển thị 3 / 3 sản phẩm' in c.value for c in app.caption))
            app.selectbox(key='stars_filter').select('4 sao').run()
            app.button(key='clear_directory_discovery').click().run()
            self.assertEqual(app.session_state['directory_discovery_messages'], [])
            self.assertEqual(app.selectbox(key='stars_filter').value, '4 sao')
            self.assertTrue(any('Hiển thị 1 / 3 sản phẩm' in c.value for c in app.caption))
            ai.side_effect = RuntimeError('service unavailable')
            app.chat_input(key='directory_discovery_question').set_value('Find tea').run()
            self.assertFalse(app.exception)
            self.assertTrue(app.error)
            self.assertTrue(any('Hiển thị 1 / 3 sản phẩm' in c.value for c in app.caption))
            self.assertTrue(any('Tea 0' in m.value for m in app.markdown))


if __name__ == '__main__':
    unittest.main()
