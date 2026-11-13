import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from data import auth, postgres, purchase, seed_purchase, suppliers
import test_suppliers as fixtures

TEST_URL = os.environ.get('TEST_DATABASE_URL')


@unittest.skipUnless(TEST_URL, 'Use the dedicated local PostgreSQL test database')
class PurchaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.SupplierIntegrationTests.setUpClass()

    clean = fixtures.SupplierIntegrationTests.clean
    create = fixtures.SupplierIntegrationTests.create
    approved = fixtures.SupplierIntegrationTests.approved

    def setUp(self):
        fixtures.SupplierIntegrationTests.setUp(self)
        self.unit_a = self.approved(self.seller, 'Test unit A')
        self.unit_b = self.approved(self.seller2, 'Test unit B')
        self.fields = dict(title='Test demand', category='Tea', description='Synthetic request for tests',
                           quantity='10', unit='box', budget='1000.00', budget_type='total',
                           delivery_location='Test province', delivery_deadline=purchase.today() + timedelta(days=7),
                           additional_requirements='', source='TIKI', product_id='001', contact_name='Test Buyer',
                           contact_email='private-buyer@example.com', contact_phone='0123456789')

    def demand(self, session=None):
        return purchase.create_request(session or self.buyer1, self.fields)

    def quote(self, request_id, match_id, session=None, **changes):
        fields = dict(quantity='10', unit='box', unit_price='50.05', shipping_fee='10',
                      expected_delivery=purchase.today() + timedelta(days=2),
                      valid_until=datetime.now(purchase.ZONE) + timedelta(days=1),
                      notes='Synthetic quote', excluded_costs='VAT not included')
        fields.update(changes)
        return purchase.submit_quote(session or self.seller, request_id, match_id, **fields)

    def test_full_flow_contacts_versions_and_owner_confirmation(self):
        request_id = self.demand()
        self.assertEqual(purchase.request_detail(self.buyer1, request_id)['request']['status'], 'open')
        match_a = purchase.assign_supplier(self.admin, request_id, self.unit_a)
        match_b = purchase.assign_supplier(self.admin, request_id, self.unit_b)
        with self.assertRaises(ValueError):
            purchase.edit_request(self.buyer1, request_id, self.fields)
        first = self.quote(request_id, match_a)
        second = self.quote(request_id, match_a, quantity='2.345', unit_price='100.05', shipping_fee='3')
        rival = self.quote(request_id, match_b, self.seller2)
        detail = purchase.request_detail(self.buyer1, request_id)
        self.assertEqual([q['version'] for q in detail['quotes'] if q['match_id'] == match_a], [1, 2])
        self.assertEqual(next(q for q in detail['quotes'] if q['id'] == first)['status'], 'superseded')
        self.assertEqual(next(q for q in detail['quotes'] if q['id'] == second)['total_amount'], Decimal('237.62'))
        for session in (self.seller, self.seller2, self.admin):
            public = json.dumps(purchase.request_detail(session, request_id), default=str)
            self.assertNotIn('private-buyer@example.com', public)
            self.assertNotIn('0123456789', public)
        with self.assertRaises(ValueError):
            purchase.select_quote(self.buyer1, request_id, first)
        purchase.select_quote(self.buyer1, request_id, second)
        winner = purchase.request_detail(self.seller, request_id)
        self.assertEqual(winner['contacts']['contact_email'], 'private-buyer@example.com')
        self.assertIsNone(purchase.request_detail(self.seller2, request_id)['contacts'])
        self.assertNotIn('private-buyer@example.com', json.dumps(purchase.request_detail(self.seller2, request_id), default=str))
        self.assertEqual({q['id'] for q in winner['quotes']}, {first, second})
        self.assertNotIn(rival, {q['id'] for q in winner['quotes']})
        for operation in (lambda: self.quote(request_id, match_a),
                          lambda: purchase.decline_request(self.seller, request_id, match_a, 'Cannot edit chosen'),
                          lambda: purchase.close_request(self.admin, request_id, 'connected')):
            with self.assertRaises((ValueError, auth.AccessDenied)):
                operation()
        purchase.close_request(self.buyer1, request_id, 'connected')
        final = purchase.request_detail(self.buyer1, request_id)
        self.assertEqual(final['request']['status'], 'connected')
        self.assertEqual(final['events'][-1]['event_type'], 'connected')

    def test_other_buyer_cannot_read_edit_choose_or_close(self):
        request_id = self.demand(self.buyer2)
        match = purchase.assign_supplier(self.admin, request_id, self.unit_a)
        quote = self.quote(request_id, match)
        self.assertEqual(purchase.list_requests(self.buyer1), [])
        for operation in (lambda: purchase.request_detail(self.buyer1, request_id),
                          lambda: purchase.edit_request(self.buyer1, request_id, self.fields),
                          lambda: purchase.select_quote(self.buyer1, request_id, quote),
                          lambda: purchase.close_request(self.buyer1, request_id, 'cancelled'),
                          lambda: purchase.assign_supplier(self.buyer1, request_id, self.unit_b)):
            with self.assertRaises(auth.AccessDenied):
                operation()

    def test_seller_scope_membership_status_and_admin_only_assignment(self):
        request_id = self.demand()
        match_b = purchase.assign_supplier(self.admin, request_id, self.unit_b)
        self.assertEqual(purchase.list_requests(self.seller), [])
        with self.assertRaises(auth.AccessDenied):
            purchase.request_detail(self.seller, request_id)
        with self.assertRaises(auth.AccessDenied):
            self.quote(request_id, match_b)
        purchase.assign_supplier(self.admin, request_id, self.unit_a)
        with self.assertRaises(auth.AccessDenied):
            self.quote(request_id, match_b)
        with self.assertRaises(auth.AccessDenied):
            purchase.assign_supplier(self.seller, request_id, self.unit_b)
        suppliers.review_application(self.admin, self.unit_b, 'suspended', 'Test suspension')
        with self.assertRaises(auth.AccessDenied):
            self.quote(request_id, match_b, self.seller2)
        pending = self.create(self.seller2, 'Pending')
        with self.assertRaises(ValueError):
            purchase.assign_supplier(self.admin, request_id, pending)
        with self.assertRaises(ValueError):
            purchase.assign_supplier(self.admin, request_id, self.unit_a)

    def test_expired_or_suspended_quote_cannot_be_selected(self):
        request_id = self.demand()
        match = purchase.assign_supplier(self.admin, request_id, self.unit_a)
        quote = self.quote(request_id, match)
        with postgres.transaction() as connection:
            connection.execute("UPDATE business.request_quotes SET valid_until=CURRENT_TIMESTAMP-INTERVAL '1 second' WHERE id=%s", (quote,))
        with self.assertRaises(ValueError):
            purchase.select_quote(self.buyer1, request_id, quote)
        quote = self.quote(request_id, match)
        suppliers.review_application(self.admin, self.unit_a, 'suspended', 'Suspended')
        with self.assertRaises(ValueError):
            purchase.select_quote(self.buyer1, request_id, quote)

    def test_two_simultaneous_selections_only_one_succeeds(self):
        request_id = self.demand()
        a = purchase.assign_supplier(self.admin, request_id, self.unit_a)
        b = purchase.assign_supplier(self.admin, request_id, self.unit_b)
        quotes = [self.quote(request_id, a), self.quote(request_id, b, self.seller2)]
        def choose(quote_id):
            try:
                purchase.select_quote(self.buyer1, request_id, quote_id)
                return 'chosen'
            except ValueError:
                return 'rejected'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(choose, quotes))
        self.assertEqual(sorted(results), ['chosen', 'rejected'])
        detail = purchase.request_detail(self.buyer1, request_id)
        self.assertEqual(sum(q['status'] == 'selected' for q in detail['quotes']), 1)
        self.assertEqual(sum(e['event_type'] == 'selected' for e in detail['events']), 1)

    def test_cancelled_and_closed_requests_reject_actions(self):
        for target in ('cancelled', 'closed_no_match'):
            request_id = self.demand()
            match = purchase.assign_supplier(self.admin, request_id, self.unit_a)
            quote = self.quote(request_id, match)
            purchase.close_request(self.buyer1, request_id, target)
            for operation in (lambda: self.quote(request_id, match),
                              lambda: purchase.select_quote(self.buyer1, request_id, quote),
                              lambda: purchase.assign_supplier(self.admin, request_id, self.unit_b),
                              lambda: purchase.edit_request(self.buyer1, request_id, self.fields),
                              lambda: purchase.decline_request(self.seller, request_id, match, 'Decline'),
                              lambda: purchase.close_request(self.buyer1, request_id, 'connected')):
                with self.assertRaises(ValueError):
                    operation()

    def test_decline_keeps_quote_history_and_allows_new_version(self):
        request_id = self.demand()
        match = purchase.assign_supplier(self.admin, request_id, self.unit_a)
        first = self.quote(request_id, match)
        purchase.decline_request(self.seller, request_id, match, 'Not enough stock')
        detail = purchase.request_detail(self.buyer1, request_id)
        self.assertEqual(detail['matches'][0]['status'], 'declined')
        self.assertEqual(detail['quotes'][0]['status'], 'superseded')
        self.assertEqual(detail['request']['status'], 'assigned')
        with self.assertRaises(ValueError):
            purchase.select_quote(self.buyer1, request_id, first)
        self.quote(request_id, match)
        detail = purchase.request_detail(self.seller, request_id)
        self.assertEqual([q['version'] for q in detail['quotes']], [1, 2])
        self.assertTrue(any(e['event_type'] == 'declined' and e['content'] == 'Not enough stock' for e in detail['events']))

    def test_validation_and_no_owner_or_total_tampering(self):
        for changes in ({'buyer_id': self.buyer2.user_id}, {'quantity': '0'}, {'budget': '-1'},
                        {'quantity': 1.5}, {'budget_type': 'invented'}, {'description': 'Call 0123456789'},
                        {'delivery_deadline': purchase.today() - timedelta(days=1)}, {'product_id': 'missing'}):
            with self.assertRaises(ValueError):
                purchase.create_request(self.buyer1, {**self.fields, **changes})
        request_id = self.demand()
        purchase.edit_request(self.buyer1, request_id, {**self.fields, 'title': 'Updated'})
        match = purchase.assign_supplier(self.admin, request_id, self.unit_a)
        for changes in ({'quantity': '11'}, {'unit': 'other'}, {'unit_price': '-1'}, {'unit_price': 0.1},
                        {'shipping_fee': '-1'}, {'excluded_costs': ''},
                        {'valid_until': datetime.now()}, {'expected_delivery': purchase.today() - timedelta(days=1)}):
            with self.assertRaises(ValueError):
                self.quote(request_id, match, **changes)
        with self.assertRaises(TypeError):
            self.quote(request_id, match, total_amount='1')
        self.assertEqual(purchase.request_detail(self.buyer1, request_id)['quotes'], [])

    def test_event_failure_rolls_back_quote_replacement_and_selection(self):
        request_id = self.demand()
        match = purchase.assign_supplier(self.admin, request_id, self.unit_a)
        quote_id = self.quote(request_id, match)
        with patch('data.purchase._event', side_effect=RuntimeError('Test rollback')):
            with self.assertRaises(RuntimeError):
                self.quote(request_id, match)
            with self.assertRaises(RuntimeError):
                purchase.select_quote(self.buyer1, request_id, quote_id)
        detail = purchase.request_detail(self.buyer1, request_id)
        self.assertEqual(len(detail['quotes']), 1)
        self.assertEqual(detail['quotes'][0]['status'], 'active')
        self.assertEqual(detail['request']['status'], 'quoted')
        self.assertIsNone(detail['request']['selected_quote_id'])

    def test_seed_open_request_twice_preserves_edits_and_does_not_match(self):
        self.assertEqual(seed_purchase.seed_request(), {'created': 1, 'skipped': 0})
        request_id = purchase.list_requests(self.buyer1)[0]['id']
        detail = purchase.request_detail(self.buyer1, request_id)
        values = {field: detail['request'][field] for field in purchase.REQUEST_FIELDS}
        values['title'] = 'Edited simulated demand'
        purchase.edit_request(self.buyer1, request_id, values)
        self.assertEqual(seed_purchase.seed_request(), {'created': 0, 'skipped': 1})
        detail = purchase.request_detail(self.buyer1, request_id)
        self.assertEqual(detail['request']['title'], 'Edited simulated demand')
        self.assertEqual(detail['request']['status'], 'open')
        self.assertEqual(detail['matches'], [])
        self.assertEqual(detail['quotes'], [])


class DecimalTests(unittest.TestCase):
    def test_cannot_choose_quote_with_past_delivery_even_if_still_valid(self):
        actor = {'id': 1, 'role': 'buyer'}
        row = dict(id=1, buyer_id=1, status='quoted', selected_quote_id=None,
                   delivery_deadline=purchase.today() + timedelta(days=7))
        quote = dict(id=2, status='active', valid_until=datetime.now(purchase.ZONE) + timedelta(days=1),
                     expected_delivery=purchase.today() - timedelta(days=1))
        with patch('data.postgres.transaction') as transaction, \
                patch('data.auth.require_user', return_value=actor), \
                patch('data.purchase._request', return_value=row), \
                patch('data.purchase._cursor') as cursor:
            cursor.return_value.execute.return_value.fetchone.return_value = quote
            with self.assertRaisesRegex(ValueError, 'Ngày giao'):
                purchase.select_quote(object(), 1, 2)
            transaction.return_value.__enter__.return_value.execute.assert_not_called()

    def test_decimal_limits_and_float_rejection(self):
        self.assertEqual(purchase.number('0'), Decimal('0.00'))
        self.assertEqual(purchase.number('1.234', 3), Decimal('1.234'))
        for value in ('NaN', 'Infinity', '-1', '1.001', '10000000000000000', 0.1):
            with self.assertRaises(ValueError):
                purchase.number(value)

