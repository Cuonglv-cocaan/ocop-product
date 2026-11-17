import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from data import auth


class AdminMatchingDashboardUITests(unittest.TestCase):
    def setUp(self):
        import streamlit as st
        st.cache_data.clear()

    def test_dashboard_blocks_buyer_and_seller_before_filters_or_data(self):
        for role in ('buyer', 'seller'):
            with self.subTest(role=role), \
                    patch('data.postgres.transaction'), \
                    patch('data.auth.require_user', side_effect=auth.AccessDenied('Chỉ admin')) as check, \
                    patch('data.suppliers.list_suppliers') as listing, \
                    patch('data.metrics.dashboard') as dashboard:
                app = AppTest.from_string('from src.dashboard_ui import page\npage()').run()
                self.assertFalse(app.exception)
                self.assertTrue(app.error)
                self.assertEqual(len(app.date_input), 0)
                self.assertEqual(check.call_args.args[2], {'admin'})
                listing.assert_not_called()
                dashboard.assert_not_called()

    def test_dashboard_empty_denominators_and_filters(self):
        result = dict(created=0, assigned=0, quoted_requests=0, selected=0, connected=0, cancelled=0, closed_no_match=0,
                      quote_rate=None, median_first_quote_hours=None, suppliers=[],
                      viewed_at=datetime(2026, 11, 11, tzinfo=timezone.utc))
        with patch('data.postgres.transaction'), patch('data.auth.require_user'), \
                patch('data.suppliers.list_suppliers', return_value=[dict(id=1, name='Test supplier')]), \
                patch('data.metrics.dashboard', return_value=result) as dashboard:
            app = AppTest.from_string('from src.dashboard_ui import page\npage()').run()
            self.assertFalse(app.exception)
            self.assertEqual([m.value for m in app.metric][-2:], ['Chưa có dữ liệu', 'Chưa có dữ liệu'])
            self.assertEqual(len(app.metric), 6)
            self.assertTrue(all(m.proto.help for m in app.metric))
            self.assertTrue(all(info.value == 'Chưa có dữ liệu' for info in app.info))
            self.assertEqual([w.label for w in app.selectbox], ['Nhà cung cấp'])
            self.assertEqual(dashboard.call_args.kwargs, dict(supplier_id=None))
            app.selectbox[0].select(1).run()
            self.assertFalse(app.exception)
            self.assertEqual(dashboard.call_args.kwargs, dict(supplier_id=1))

    def test_dashboard_funnel_and_kpis_use_filtered_cohort_counts(self):
        result = dict(created=5, assigned=5, quoted_requests=1, selected=3, connected=2,
                      cancelled=1, closed_no_match=0, quote_rate=.2, median_first_quote_hours=0,
                      suppliers=[dict(supplier_name='A', assigned=5, responded=1, quoted=1,
                                      median_response_hours=None)],
                      viewed_at=datetime(2026, 11, 11, tzinfo=timezone.utc))
        with patch('data.postgres.transaction'), patch('data.auth.require_user'), \
                patch('data.suppliers.list_suppliers', return_value=[dict(id=1, name='A')]), \
                patch('data.metrics.dashboard', return_value=result):
            app = AppTest.from_string('from src.dashboard_ui import page\npage()').run()
            self.assertFalse(app.exception)
            self.assertEqual([m.value for m in app.metric], ['5', '5', '1', '2', '20.0%', '0.00'])
            charts = app.get('vega_lite_chart') or app.get('arrow_vega_lite_chart')
            self.assertEqual(len(charts), 1)
            self.assertEqual(app.dataframe[0].value.iloc[0]['Trung vị phản hồi (giờ)'], 'Chưa có dữ liệu')
            app.selectbox[0].select(1).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('bước sau có thể lớn hơn' in c.value for c in app.caption))

    def test_funnel_does_not_clamp_supplier_filtered_outcomes(self):
        from src.dashboard_ui import _funnel
        result = dict(created=5, assigned=5, quoted_requests=1, selected=3, connected=2)
        with patch('src.dashboard_ui.st.subheader'), patch('src.dashboard_ui.st.caption'), \
                patch('src.dashboard_ui.st.vega_lite_chart') as chart:
            _funnel(result)
        values = chart.call_args.kwargs['spec']['data']['values']
        self.assertEqual([v['count'] for v in values], [5, 5, 1, 3, 2])
        self.assertEqual(values[-1]['share'], .4)

    def test_matching_display_is_read_only_and_requires_confirmation(self):
        candidate = dict(supplier_id=1, supplier_name='A', is_demo=False, score=75,
                         group='confirmation', rule_version='rules-v1', products=[
                             dict(source='TIKI', product_id='001', category='Tea', group='confirmation',
                                  criteria=[dict(state='unknown', reason='Thiếu thời gian chuẩn bị', points=0)])])
        source = '''import streamlit as st
from src.purchase_ui import _matching
try:
    _matching(None, {'id': 1}, [])
except ValueError as error:
    st.error(str(error))
'''
        with patch('data.matching.find_candidates', return_value=[candidate]) as find, \
                patch('data.suppliers.catalog_items', return_value=[]), \
                patch('data.purchase.assign_supplier') as assign:
            app = AppTest.from_string(source).run()
            find.assert_not_called()
            app.checkbox[0].check().run()
            self.assertFalse(app.exception)
            assign.assert_not_called()
            app.run()
            assign.assert_not_called()
            app.button[0].click().run()
            self.assertTrue(app.error)
            assign.assert_not_called()
            app.checkbox[1].check()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            assign.assert_called_once_with(None, 1, 1, use_matching=True)


if __name__ == '__main__':
    unittest.main()
