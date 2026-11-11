import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb
import psycopg
from data import accounts, auth, database, postgres, seed_suppliers, suppliers
import test_auth as auth_fixtures

TEST_URL = os.environ.get('TEST_DATABASE_URL')


@unittest.skipUnless(TEST_URL, 'Use dedicated local PostgreSQL test database')
class SupplierIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        auth_fixtures.AuthIntegrationTests.setUpClass()

    clean = auth_fixtures.AuthIntegrationTests.clean

    def setUp(self):
        auth_fixtures.AuthIntegrationTests.setUp(self)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.catalog = Path(temp.name) / 'test.duckdb'
        config = patch.object(database, 'DUCKDB_PATH', self.catalog)
        config.start()
        self.addCleanup(config.stop)
        with duckdb.connect(str(self.catalog)) as connection:
            database.initialize_products(connection)
            connection.execute("INSERT INTO products(source,product_id,product_name) VALUES ('TIKI','001','Test tea'),('TIKTOK','001','Test honey')")
        self.seller2 = auth.authenticate('seller02', self.password)

    def create(self, session, name='Test unit'):
        return suppliers.create_application(session, {'name': name})

    def approved(self, session, name='Approved unit'):
        supplier_id = self.create(session, name)
        suppliers.review_application(self.admin, supplier_id, 'approved')
        return supplier_id

    def test_buyer_application_rejection_resubmission_and_approval(self):
        supplier_id = self.create(self.buyer1)
        row = suppliers.get_supplier(self.buyer1, supplier_id)
        self.assertEqual((row['status'], row['province'], row['reviewed_by']), ('pending', '', None))
        self.assertEqual(auth.current_user(self.buyer1)['role'], 'buyer')
        with self.assertRaises(auth.AccessDenied):
            suppliers.review_application(self.buyer1, supplier_id, 'approved')
        with self.assertRaises(ValueError):
            suppliers.create_application(self.buyer1, {'name': 'Spoof', 'status': 'approved'})
        with self.assertRaises(ValueError):
            suppliers.review_application(self.admin, supplier_id, 'rejected')
        suppliers.review_application(self.admin, supplier_id, 'rejected', 'Need details')
        suppliers.edit_profile(self.buyer1, supplier_id, {'name': 'Revised'})
        self.assertEqual(suppliers.get_supplier(self.buyer1, supplier_id)['status'], 'rejected')
        suppliers.edit_profile(self.buyer1, supplier_id, {'name': 'Resubmitted'}, resubmit=True)
        self.assertEqual(suppliers.get_supplier(self.buyer1, supplier_id)['status'], 'pending')
        suppliers.review_application(self.admin, supplier_id, 'approved')
        row = suppliers.get_supplier(self.buyer1, supplier_id)
        self.assertEqual((row['status'], row['reviewed_by']), ('approved', self.admin.user_id))
        self.assertIsNotNone(row['reviewed_at'])
        self.assertEqual(auth.current_user(self.buyer1)['role'], 'seller')
        suppliers.save_product(self.buyer1, supplier_id, 'TIKI', '001')

    def test_seller_cannot_read_admin_or_other_supplier_data_or_write_products(self):
        unit_a = self.approved(self.seller, 'Unit A')
        unit_b = self.approved(self.seller2, 'Unit B')
        suppliers.save_product(self.seller2, unit_b, 'TIKI', '001')
        for operation in (
            lambda: suppliers.list_suppliers(self.seller, admin=True),
            lambda: suppliers.get_supplier(self.seller, unit_b),
            lambda: suppliers.list_products(self.seller, unit_b),
            lambda: suppliers.edit_profile(self.seller, unit_b, {'name': 'Forbidden'}),
            lambda: suppliers.save_product(self.seller, unit_b, 'TIKI', '001'),
            lambda: suppliers.stop_product(self.seller, unit_b, 'TIKI', '001'),
            lambda: suppliers.review_application(self.seller, unit_a, 'suspended', 'Spoof'),
        ):
            with self.assertRaises(auth.AccessDenied):
                operation()
        self.assertEqual([r['id'] for r in suppliers.list_suppliers(self.seller)], [unit_a])
        self.assertEqual(suppliers.get_supplier(self.seller2, unit_b)['name'], 'Unit B')
        self.assertTrue(suppliers.list_products(self.seller2, unit_b)[0]['is_active'])

    def test_pending_and_suspended_block_selling_and_role_alone_is_insufficient(self):
        unit = self.create(self.seller)
        with self.assertRaises(auth.AccessDenied):
            suppliers.save_product(self.seller, unit, 'TIKI', '001')
        suppliers.review_application(self.admin, unit, 'approved')
        suppliers.save_product(self.seller, unit, 'TIKI', '001')
        suppliers.review_application(self.admin, unit, 'suspended', 'Review required')
        for operation in (
            lambda: suppliers.save_product(self.seller, unit, 'TIKI', '001'),
            lambda: suppliers.stop_product(self.seller, unit, 'TIKI', '001'),
            lambda: suppliers.edit_profile(self.seller, unit, {'name': 'Blocked'}),
        ):
            with self.assertRaises(auth.AccessDenied):
                operation()
        self.assertEqual(auth.current_user(self.seller)['role'], 'seller')
        suppliers.review_application(self.admin, unit, 'approved')
        suppliers.stop_product(self.seller, unit, 'TIKI', '001')

    def test_suspension_of_one_unit_does_not_remove_other_unit_access(self):
        unit_a = self.approved(self.seller, 'A')
        unit_b = self.approved(self.seller, 'B')
        suppliers.review_application(self.admin, unit_a, 'suspended', 'Pause A')
        self.assertEqual(auth.current_user(self.seller)['role'], 'seller')
        suppliers.save_product(self.seller, unit_b, 'TIKI', '001')
        with self.assertRaises(auth.AccessDenied):
            suppliers.save_product(self.seller, unit_a, 'TIKI', '001')

    def test_composite_product_keys_validation_and_history(self):
        unit = self.approved(self.seller)
        for source in ('TIKI', 'TIKTOK'):
            suppliers.save_product(self.seller, unit, source, '001', minimum_order='2.5')
        suppliers.save_product(self.seller, unit, ' tiki ', '001', minimum_order='3', unit='box')
        self.assertEqual(len(suppliers.list_products(self.seller, unit)), 2)
        for kwargs in ({'minimum_order': 'NaN'}, {'minimum_order': '0'}, {'minimum_order': '-1'}):
            with self.assertRaises(ValueError):
                suppliers.save_product(self.seller, unit, 'TIKI', '001', **kwargs)
        with self.assertRaises(ValueError):
            suppliers.save_product(self.seller, unit, 'TIKI', 'missing')
        with duckdb.connect(str(self.catalog)) as connection:
            connection.execute('DELETE FROM products')
        rows = suppliers.list_products(self.seller, unit)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r['product_name'] == 'Sản phẩm không còn trong catalog' for r in rows))
        suppliers.stop_product(self.seller, unit, 'TIKI', '001')
        self.assertFalse(suppliers.list_products(self.seller, unit)[0]['is_active'])

    def test_seed_twice_does_not_overwrite_edited_aggregates(self):
        self.assertEqual(seed_suppliers.seed_suppliers(), {'created': 2, 'skipped': 0})
        unit_a = suppliers.list_suppliers(self.seller)[0]['id']
        unit_b = suppliers.list_suppliers(self.seller2)[0]['id']
        self.assertNotEqual(unit_a, unit_b)
        self.assertTrue(suppliers.get_supplier(self.seller, unit_a)['is_demo'])
        suppliers.edit_profile(self.seller, unit_a, {'name': 'Edited unit'})
        products = suppliers.list_products(self.seller, unit_a)
        suppliers.save_product(self.seller, unit_a, products[0]['source'], products[0]['product_id'], capacity_description='Edited capacity')
        suppliers.review_application(self.admin, unit_a, 'suspended', 'Keep suspended')
        self.assertEqual(seed_suppliers.seed_suppliers(), {'created': 0, 'skipped': 2})
        row = suppliers.get_supplier(self.seller, unit_a)
        self.assertEqual((row['name'], row['status']), ('Edited unit', 'suspended'))
        self.assertEqual(suppliers.list_products(self.seller, unit_a)[0]['capacity_description'], 'Edited capacity')
        with postgres.transaction() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM business.supplier_members').fetchone()[0], 2)
            self.assertEqual(connection.execute('SELECT count(*) FROM business.supplier_products').fetchone()[0], 2)

    def test_seed_missing_accounts_or_catalog_is_atomic(self):
        with postgres.transaction() as connection:
            connection.execute("DELETE FROM business.users WHERE username='seller02'")
        with self.assertRaisesRegex(ValueError, 'seller02'):
            seed_suppliers.seed_suppliers()
        with postgres.transaction() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM business.suppliers').fetchone()[0], 0)
        with duckdb.connect(str(self.catalog)) as connection:
            connection.execute('DELETE FROM products')
        with self.assertRaisesRegex(ValueError, '2'):
            seed_suppliers.seed_suppliers()

    def test_membership_unique_and_removal_or_inactive_account_blocks_access(self):
        unit = self.approved(self.seller)
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with postgres.transaction() as connection:
                connection.execute('INSERT INTO business.supplier_members(supplier_id,user_id) VALUES (%s,%s)',
                                   (unit, self.seller.user_id))
        with postgres.transaction() as connection:
            connection.execute('DELETE FROM business.supplier_members WHERE supplier_id=%s', (unit,))
        with self.assertRaises(auth.AccessDenied):
            suppliers.save_product(self.seller, unit, 'TIKI', '001')
        with self.assertRaises(auth.AccessDenied):
            suppliers.get_supplier(self.seller, unit)
        with self.assertRaises(auth.AccessDenied):
            suppliers.list_suppliers(None)
        accounts.set_active(self.admin, self.seller.user_id, False)
        with self.assertRaises(auth.AccessDenied):
            suppliers.list_suppliers(self.seller)

