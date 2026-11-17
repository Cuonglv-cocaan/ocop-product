import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest
from data.database import COLUMNS


APP = str(Path(__file__).resolve().parents[1] / 'src/app.py')


class NavigationTests(unittest.TestCase):
    def setUp(self):
        import streamlit as st
        st.cache_data.clear()
        row = dict.fromkeys(COLUMNS, '')
        row.update(source='TIKI', product_id='1', product_name='Tea', province_name='Hà Nội')
        catalog = patch('data.database.read_products', return_value=pd.DataFrame([row]))
        catalog.start()
        self.addCleanup(catalog.stop)

    def test_products_deep_link_and_live_url_changes(self):
        app = AppTest.from_file(APP)
        app.query_params['page'] = 'products'
        app.query_params['campaign'] = 'demo'
        app.run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['page'], 'Sản phẩm OCOP')
        self.assertEqual(app.session_state['navigation_page'], 'Sản phẩm OCOP')
        app.query_params['page'] = 'regions'
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['page'], 'Vùng miền')
        app.button(key='logo_home').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.query_params['page'], ['home'])
        self.assertEqual(app.query_params['campaign'], ['demo'])

    def test_login_guest_action_opens_demand_without_authentication(self):
        with patch('data.auth.authenticate') as authenticate:
            app = AppTest.from_file(APP)
            app.query_params['page'] = 'login'
            app.session_state['purchase_reference'] = {'title': 'Tea', 'source': 'TIKI', 'product_id': '1'}
            app.run(timeout=20)
            app.button(key='guest_demand').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['page'], 'Nhu cầu mua hàng')
            self.assertEqual(app.query_params['page'], ['demand'])
            self.assertNotIn('auth_session', app.session_state)
            self.assertEqual(app.session_state['purchase_reference']['title'], 'Tea')
            authenticate.assert_not_called()

    def test_logo_preserves_authenticated_session_for_each_role(self):
        for role in ('buyer', 'seller', 'admin'):
            with self.subTest(role=role), patch('data.auth.current_user', return_value={
                    'id': 1, 'username': 'demo', 'role': role}):
                session = object()
                app = AppTest.from_file(APP)
                app.session_state['auth_session'] = session
                app.session_state['private_note'] = 'Keep this draft'
                app.query_params['page'] = 'products'
                app.run(timeout=20)
                app.button(key='logo_home').click().run()
                self.assertFalse(app.exception)
                self.assertIs(app.session_state['auth_session'], session)
                self.assertEqual(app.session_state['private_note'], 'Keep this draft')
                self.assertEqual(app.session_state['page'], 'Trang chủ')
                self.assertEqual(app.query_params['page'], ['home'])

    def test_internal_navigation_updates_url_without_being_overridden(self):
        app = AppTest.from_file(APP)
        app.query_params['page'] = 'home'
        app.run(timeout=20)
        next(b for b in app.button if b.label == 'Khám phá sản phẩm →').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['page'], 'Sản phẩm OCOP')
        self.assertEqual(app.query_params['page'], ['products'])

    def test_unavailable_and_unknown_slugs_cannot_bypass_roles(self):
        with patch('src.dashboard_ui.page') as dashboard, patch('src.purchase_ui.page') as purchase:
            for slug in ('admin', 'dashboard', 'supply', 'unknown'):
                with self.subTest(slug=slug):
                    app = AppTest.from_file(APP)
                    app.query_params['page'] = slug
                    app.run(timeout=20)
                    self.assertFalse(app.exception)
                    self.assertEqual(app.session_state['page'], 'Trang chủ')
                    self.assertEqual(app.query_params['page'], ['home'])
            dashboard.assert_not_called()
            purchase.assert_not_called()
