import os
import secrets
import unittest
from dataclasses import replace
from unittest.mock import patch

import psycopg
from psycopg.conninfo import conninfo_to_dict
from data import accounts, auth, leads, postgres

TEST_URL = os.environ.get('TEST_DATABASE_URL')


class SessionTests(unittest.TestCase):
    def test_logout_clears_credentials_drafts_and_private_data(self):
        state = {'auth_session': object(), 'login_password': secrets.token_urlsafe(10),
                 'private_note': 'private', 'directory_discovery_messages': ['private']}
        auth.logout(state)
        self.assertEqual(state, {})

    def test_username_normalization(self):
        self.assertEqual(auth.normalize_username(' Buyer01 '), 'buyer01')
        for value in ('ab', 'user@site', 'a b', 'Đemo'):
            with self.assertRaises(ValueError):
                auth.normalize_username(value)


@unittest.skipUnless(TEST_URL, 'Set TEST_DATABASE_URL for isolated local PostgreSQL tests')
class AuthIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = conninfo_to_dict(TEST_URL)
        if config.get('host') not in ('localhost', '127.0.0.1') or config.get('dbname') != 'ocop_leads_test':
            raise ValueError('Use only the dedicated local ocop_leads_test database')

    def setUp(self):
        env = patch.dict(os.environ, {'DATABASE_URL': TEST_URL, 'LEADS_BACKEND': 'postgres'})
        env.start()
        self.addCleanup(env.stop)
        with postgres.transaction() as connection:
            connection.execute('DROP SCHEMA IF EXISTS business CASCADE')
        self.addCleanup(self.clean)
        postgres.initialize_schema()
        self.password = secrets.token_urlsafe(18)
        accounts.seed_accounts(self.password)
        self.buyer1 = auth.authenticate('buyer01', self.password)
        self.buyer2 = auth.authenticate('buyer02', self.password)
        self.seller = auth.authenticate('seller01', self.password)
        self.admin = auth.authenticate('admin01', self.password)

    def clean(self):
        with postgres.transaction() as connection:
            connection.execute('DROP SCHEMA IF EXISTS business CASCADE')

    def save(self, session, role='buyer'):
        return leads.save_lead(leads.KINDS[role], 'Demo', 'demo@example.com', '0', 'Note', session=session)

    def test_login_correct_wrong_unknown_and_inactive(self):
        self.assertEqual(auth.authenticate(' BUYER01 ', self.password).user_id, self.buyer1.user_id)
        for username, password in [('buyer01', secrets.token_urlsafe(18)), ('unknown', self.password)]:
            with self.assertRaises(auth.AccessDenied):
                auth.authenticate(username, password)
        accounts.set_active(self.admin, self.buyer1.user_id, False)
        with self.assertRaises(auth.AccessDenied):
            auth.authenticate('buyer01', self.password)
        with self.assertRaises(auth.AccessDenied):
            leads.read_leads(self.buyer1)
        with self.assertRaises(auth.AccessDenied):
            self.save(self.buyer1)

    def test_buyer_cannot_read_or_edit_other_buyers_lead(self):
        own = self.save(self.buyer1)
        other = self.save(self.buyer2)
        self.assertEqual([r['id'] for r in leads.read_leads(self.buyer1)], [own])
        self.assertEqual(leads.read_leads(self.buyer1, other), [])
        with self.assertRaises(auth.AccessDenied):
            leads.update_note(self.buyer1, other, 'Forbidden')
        leads.update_note(self.buyer1, own, 'Updated')
        self.assertEqual(leads.read_leads(self.buyer2, other)[0]['note'], 'Note')

    def test_seller_permissions_and_admin_functions(self):
        buyer_lead = self.save(self.buyer1)
        # Existing seller leads remain readable; new registrations use supplier profiles.
        with postgres.transaction() as connection:
            seller_lead = connection.execute('''INSERT INTO business.leads(kind,name,email,phone,note,user_id)
                VALUES (%s,'Legacy seller','demo@example.com','0','Note',%s) RETURNING id''',
                (leads.KINDS['seller'], self.seller.user_id)).fetchone()[0]
        self.assertEqual([r['id'] for r in leads.read_leads(self.seller)], [seller_lead])
        self.assertEqual(leads.read_leads(self.seller, buyer_lead), [])
        with self.assertRaises(auth.AccessDenied):
            self.save(self.seller, 'buyer')
        with self.assertRaises(auth.AccessDenied):
            self.save(self.seller, 'seller')
        for session in (self.buyer1, self.seller):
            with self.assertRaises(auth.AccessDenied):
                accounts.list_accounts(session)
            with self.assertRaises(auth.AccessDenied):
                accounts.set_active(session, self.buyer2.user_id, False)
        self.assertEqual(len(accounts.list_accounts(self.admin)), 5)
        self.assertEqual(len(leads.read_leads(self.admin)), 2)
        leads.update_note(self.admin, buyer_lead, 'Reviewed')

    def test_legacy_leads_remain_unowned_and_only_admin_reads(self):
        with postgres.transaction() as connection:
            legacy_id = connection.execute("""INSERT INTO business.leads(kind,name,email,phone,note)
                VALUES ('old','Legacy','legacy@example.com','0','Unassigned') RETURNING id""").fetchone()[0]
        postgres.initialize_schema()
        for session in (self.buyer1, self.buyer2, self.seller):
            self.assertEqual(leads.read_leads(session, legacy_id), [])
            with self.assertRaises(auth.AccessDenied):
                leads.update_note(session, legacy_id, 'Forbidden')
        self.assertIsNone(leads.read_leads(self.admin, legacy_id)[0]['user_id'])

    def test_seed_twice_preserves_password_role_and_status(self):
        accounts.set_active(self.admin, self.buyer2.user_id, False)
        with postgres.transaction() as connection:
            before = connection.execute('SELECT username,password_hash,role,active FROM business.users ORDER BY id').fetchall()
        report = accounts.seed_accounts(secrets.token_urlsafe(18))
        self.assertEqual(report, {'created': 0, 'skipped': 5})
        with postgres.transaction() as connection:
            after = connection.execute('SELECT username,password_hash,role,active FROM business.users ORDER BY id').fetchall()
        self.assertEqual(before, after)
        self.assertTrue(all(row[1].startswith('$argon2id$') for row in after))
        self.assertNotIn(self.password, [row[1] for row in after])
        auth.authenticate('buyer01', self.password)

    def test_password_reset_invalidates_existing_session(self):
        password = secrets.token_urlsafe(18)
        accounts.reset_password(' BUYER01 ', password)
        with self.assertRaises(auth.AccessDenied):
            leads.read_leads(self.buyer1)
        with self.assertRaises(auth.AccessDenied):
            auth.authenticate('buyer01', self.password)
        auth.authenticate('buyer01', password)

    def test_session_identity_cannot_be_forged_and_role_is_reloaded(self):
        for session in (None, {'user_id': self.admin.user_id, 'role': 'admin'},
                        replace(self.buyer1, user_id=self.admin.user_id)):
            with self.assertRaises(auth.AccessDenied):
                accounts.list_accounts(session)
            with self.assertRaises(auth.AccessDenied):
                leads.read_leads(session)
            with self.assertRaises(auth.AccessDenied):
                self.save(session)
        # Role changes are effective immediately, without trusting stale UI state.
        with postgres.transaction() as connection:
            connection.execute("UPDATE business.users SET role='seller' WHERE id=%s", (self.buyer1.user_id,))
        with self.assertRaises(auth.AccessDenied):
            self.save(self.buyer1, 'buyer')

    def test_normalized_username_is_unique(self):
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with postgres.transaction() as connection:
                connection.execute('INSERT INTO business.users(username,password_hash,role) VALUES (%s,%s,%s)',
                                   (auth.normalize_username(' BUYER01 '), auth.HASHER.hash(self.password), 'buyer'))
