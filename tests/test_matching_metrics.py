import os
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from data import auth, matching, metrics, postgres, purchase, suppliers


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 11, 11)
        self.request = dict(source='TIKI', product_id='001', category='Trà', quantity=Decimal('10'),
                            unit='hộp', delivery_region='Hồ Chí Minh', budget=Decimal('1000'),
                            budget_type='total', delivery_deadline=date(2026, 11, 18))
        self.product = dict(supplier_id=1, supplier_name='A', supplier_status='approved', is_demo=False,
                            source='TIKI', product_id='001', category='Trà', is_active=True,
                            service_regions=['Hồ Chí Minh'], minimum_order=Decimal('5'), unit='hộp',
                            preparation_days=2, reference_price=Decimal('50'), reference_price_unit='hộp')

    def evaluate(self, **changes):
        return matching.rank_candidates(self.request, [dict(self.product, **changes)], as_of=self.today)[0]

    def test_complete_missing_units_budget_deadline_and_status(self):
        self.assertEqual((self.evaluate()['group'], self.evaluate()['score']), ('recommended', 100))
        for changes, criterion in [({'service_regions': []}, 'region'), ({'unit': 'kg'}, 'minimum'),
                                    ({'minimum_order': None}, 'minimum'), ({'preparation_days': None}, 'preparation'),
                                    ({'reference_price_unit': 'kg'}, 'budget')]:
            candidate = self.evaluate(**changes)
            self.assertEqual(candidate['group'], 'confirmation')
            self.assertEqual(next(c['state'] for c in candidate['criteria'] if c['criterion'] == criterion), 'unknown')
        for changes in [{'reference_price': Decimal('101')}, {'preparation_days': 8},
                        {'minimum_order': Decimal('11')}, {'service_regions': ['Hà Nội']},
                        {'source': 'TIKTOK', 'category': 'Mật ong'}]:
            self.assertEqual(self.evaluate(**changes)['group'], 'excluded')
        for changes in [{'supplier_status': 'suspended'}, {'supplier_status': 'pending'}, {'is_active': False}]:
            self.assertEqual(matching.rank_candidates(self.request, [dict(self.product, **changes)]), [])

    def test_group_deduplication_stable_ties_and_no_catalog_inference(self):
        other = dict(self.product, supplier_id=2, supplier_name='B')
        duplicate = dict(self.product, product_id='002', preparation_days=90)
        products = [other, duplicate, self.product]
        first = matching.rank_candidates(self.request, products, as_of=self.today)
        second = matching.rank_candidates(self.request, reversed(products), as_of=self.today)
        self.assertEqual(first, second)
        self.assertEqual([c['supplier_id'] for c in first], [1, 2])
        self.assertEqual(len(first[0]['products']), 2)
        unknown = self.evaluate(reference_price=None, preparation_days=None,
                                preparation_time='2 ngày', price=Decimal('1'), ocop_stars=5)
        self.assertEqual(unknown['group'], 'confirmation')
        self.assertEqual(unknown['score'], 75)
        self.request['budget'] = None
        self.assertEqual(self.evaluate()['score'], 90)
        self.assertEqual(self.evaluate()['group'], 'recommended')
        self.request['budget_type'] = 'per_unit'
        self.request['budget'] = Decimal('50')
        self.assertEqual(self.evaluate()['group'], 'recommended')

    def test_structured_validation(self):
        for fields in [{'preparation_days': '2 ngày'}, {'preparation_days': -1},
                       {'reference_price': '10'}, {'reference_price': 'NaN'},
                       {'service_regions': 'Toàn quốc'}, {'reference_price': 1.5}]:
            with self.assertRaises(ValueError):
                suppliers.declaration_values(fields)
        values = suppliers.declaration_values({'preparation_days': '0', 'reference_price': '0',
                                               'reference_price_unit': 'hộp', 'service_regions': ['Hà Nội']})
        self.assertEqual(values[2:4], (0, Decimal('0.00')))


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.at = datetime(2026, 11, 11, tzinfo=timezone.utc)
        self.requests = [dict(id=i, is_demo=False, status=status, selected_quote_id=None)
                         for i, status in [(1, 'connected'), (2, 'cancelled'), (3, 'closed_no_match'), (4, 'open')]]
        self.requests[0]['selected_quote_id'] = 2
        self.matches = [dict(id=mid, request_id=rid, supplier_id=sid, supplier_name=f'S{sid}',
                             supplier_is_demo=False, assigned_at=self.at + timedelta(hours=hours))
                        for mid, rid, sid, hours in [(1, 1, 1, 0), (2, 1, 2, 1), (3, 2, 1, 0)]]
        self.quotes = [dict(request_id=1, match_id=mid, created_at=self.at + timedelta(hours=h))
                       for mid, h in [(1, 2), (1, 4), (2, 5)]]
        self.events = [dict(request_id=2, match_id=3, event_type='declined', created_at=self.at + timedelta(hours=1)),
                       dict(request_id=1, match_id=1, event_type='selected', created_at=self.at + timedelta(hours=6))]

    def test_hand_calculated_distinct_requests_and_assignment_responses(self):
        result = metrics.summarize(self.requests, self.matches, self.quotes, self.events)
        self.assertEqual({k: result[k] for k in ('created', 'assigned', 'quoted_requests', 'selected', 'connected',
                                               'cancelled', 'closed_no_match')},
                         dict(created=4, assigned=2, quoted_requests=1, selected=1, connected=1,
                              cancelled=1, closed_no_match=1))
        self.assertEqual(result['quote_rate'], .5)
        self.assertEqual(result['median_first_quote_hours'], 3)
        a, b = result['suppliers']
        self.assertEqual((a['assigned'], a['responded'], a['quoted'], a['median_response_hours']), (2, 2, 1, 1.5))
        self.assertEqual((b['assigned'], b['responded'], b['quoted'], b['median_response_hours']), (1, 1, 1, 4))
        filtered = metrics.summarize(self.requests, self.matches, self.quotes, self.events, supplier_id=2)
        self.assertEqual((filtered['created'], filtered['assigned'], filtered['quote_rate'], filtered['median_first_quote_hours']),
                         (1, 1, 1, 4))

    def test_empty_and_all_records_included_regardless_of_legacy_flags(self):
        result = metrics.summarize([], [], [], [])
        self.assertIsNone(result['quote_rate'])
        self.assertIsNone(result['median_first_quote_hours'])
        self.matches[1]['supplier_is_demo'] = True
        self.requests[3]['is_demo'] = True
        result = metrics.summarize(self.requests, self.matches, self.quotes, self.events)
        self.assertEqual((result['created'], result['quoted_requests']), (4, 1))
        filtered = metrics.summarize(self.requests, self.matches, self.quotes, self.events, supplier_id=2)
        self.assertEqual((filtered['created'], filtered['quoted_requests']), (1, 1))

    def test_first_decline_remains_first_response_after_quote_versions(self):
        self.events.append(dict(request_id=1, match_id=1, event_type='declined',
                                created_at=self.at + timedelta(minutes=30)))
        result = metrics.summarize(self.requests, self.matches, self.quotes, self.events)
        supplier = result['suppliers'][0]
        self.assertEqual((supplier['responded'], supplier['quoted'], supplier['median_response_hours']), (2, 1, .75))
        self.assertEqual(result['median_first_quote_hours'], 3)


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Dedicated local PostgreSQL required')
class MatchingMetricsIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_purchase
        test_purchase.PurchaseIntegrationTests.setUpClass()

    def setUp(self):
        import test_purchase
        fixture = test_purchase.PurchaseIntegrationTests
        for name in ('clean', 'create', 'approved', 'demand', 'quote'):
            setattr(self, name, getattr(fixture, name).__get__(self))
        fixture.setUp(self)
        self.fields['delivery_region'] = 'Hồ Chí Minh'

    def supply(self, **changes):
        declarations = dict(category='Tea', service_regions=['Hồ Chí Minh'], preparation_days='2',
                            reference_price='50', reference_price_unit='box')
        declarations.update(changes)
        suppliers.save_product(self.seller, self.unit_a, 'TIKI', '001', minimum_order='5', unit='box', structured=declarations)

    def test_matching_is_read_only_snapshot_and_status_recheck(self):
        rid = self.demand()
        self.supply()
        suppliers.save_product(self.seller, self.unit_a, 'TIKTOK', '001')
        before = purchase.request_detail(self.admin, rid)
        for _ in range(2):
            candidates = matching.find_candidates(self.admin, rid)
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]['score'], 100)
        after = purchase.request_detail(self.admin, rid)
        self.assertEqual(before, after)
        mid = purchase.assign_supplier(self.admin, rid, self.unit_a, use_matching=True)
        snapshot = purchase.request_detail(self.admin, rid)['matches'][0]['matching_snapshot']
        self.assertEqual(snapshot['rule_version'], matching.VERSION)
        self.supply(reference_price='999')
        self.assertEqual(snapshot, purchase.request_detail(self.admin, rid)['matches'][0]['matching_snapshot'])
        suppliers.stop_product(self.seller, self.unit_a, 'TIKTOK', '001')
        rid2 = self.demand()
        with self.assertRaises(ValueError):
            purchase.assign_supplier(self.admin, rid2, self.unit_a, use_matching=True)
        # Ordinary manual assignment still allows admin judgement.
        purchase.assign_supplier(self.admin, rid2, self.unit_a)
        suppliers.review_application(self.admin, self.unit_a, 'suspended', 'Test suspension')
        self.assertEqual(matching.find_candidates(self.admin, rid2), [])

    def test_dashboard_cohort_boundaries_and_permissions(self):
        rid = self.demand()
        first = purchase.assign_supplier(self.admin, rid, self.unit_a)
        second = purchase.assign_supplier(self.admin, rid, self.unit_b)
        self.quote(rid, first)
        self.quote(rid, first)
        purchase.decline_request(self.seller2, rid, second, 'Test refusal')
        with postgres.transaction() as connection:
            # 17:00 UTC = following day's midnight in Vietnam.
            connection.execute("UPDATE business.purchase_requests SET created_at='2026-11-10 17:00:00+00' WHERE id=%s", (rid,))
        day = date(2026, 11, 11)
        result = metrics.dashboard(self.admin, day, day)
        self.assertEqual((result['created'], result['assigned'], result['quoted_requests'], result['quote_rate']), (1, 1, 1, 1))
        self.assertEqual([s['quoted'] for s in result['suppliers']], [1, 0])
        self.assertEqual([s['responded'] for s in result['suppliers']], [1, 1])
        self.assertEqual(metrics.dashboard(self.admin, day - timedelta(days=1), day - timedelta(days=1))['created'], 0)
        for session in (self.buyer1, self.seller, self.seller2):
            with self.assertRaises(auth.AccessDenied):
                metrics.dashboard(session, day, day)
            with self.assertRaises(auth.AccessDenied):
                matching.find_candidates(session, rid)
        with self.assertRaises(ValueError):
            metrics.dashboard(self.admin, day, day - timedelta(days=1))

    def test_snapshot_assignment_rollback_and_confirmation_group(self):
        rid = self.demand()
        self.supply(preparation_days='')
        self.assertEqual(matching.find_candidates(self.admin, rid)[0]['group'], 'confirmation')
        with patch('data.purchase._event', side_effect=ValueError('Test event failure')):
            with self.assertRaises(ValueError):
                purchase.assign_supplier(self.admin, rid, self.unit_a, use_matching=True)
        detail = purchase.request_detail(self.admin, rid)
        self.assertEqual(detail['matches'], [])
        self.assertEqual(detail['request']['status'], 'open')
        purchase.assign_supplier(self.admin, rid, self.unit_a, use_matching=True)
        match = purchase.request_detail(self.admin, rid)['matches'][0]
        self.assertEqual(match['matching_snapshot']['group'], 'confirmation')

    def test_legacy_upgrade_does_not_infer_declarations_and_marks_demo(self):
        rid = self.demand()
        suppliers.save_product(self.seller, self.unit_a, 'TIKI', '001', preparation_time='2 ngày')
        with postgres.transaction() as connection:
            # Recreate the pre-006 shape only in the dedicated, disposable test DB.
            connection.execute('''ALTER TABLE business.supplier_products DROP COLUMN category,
                DROP COLUMN service_regions,DROP COLUMN preparation_days,DROP COLUMN reference_price,
                DROP COLUMN reference_price_unit''')
            connection.execute('ALTER TABLE business.purchase_requests DROP COLUMN delivery_region,DROP COLUMN is_demo')
            connection.execute('ALTER TABLE business.request_matches DROP COLUMN matching_snapshot,DROP COLUMN rule_version')
            connection.execute('DROP INDEX business.request_events_match_type_idx')
            connection.execute('DROP INDEX business.purchase_requests_created_idx')
            connection.execute("DELETE FROM business.schema_migrations WHERE version='006_matching_metrics.sql'")
            connection.execute("UPDATE business.purchase_requests SET demo_key='legacy-demo' WHERE id=%s", (rid,))
        postgres.initialize_schema()
        postgres.initialize_schema()
        product = suppliers.list_products(self.seller, self.unit_a)[0]
        self.assertEqual(product['preparation_time'], '2 ngày')
        self.assertIsNone(product['preparation_days'])
        self.assertEqual(product['service_regions'], [])
        self.assertIsNone(product['reference_price'])
        self.assertTrue(purchase.request_detail(self.admin, rid)['request']['is_demo'])


if __name__ == '__main__':
    unittest.main()
