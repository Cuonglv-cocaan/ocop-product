"""Opt-in integration tests, restricted to a dedicated local test database."""
import os
import io
import json
from contextlib import closing
from contextlib import redirect_stdout
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.conninfo import conninfo_to_dict

from data import accounts, auth, leads, migrate_leads, postgres


TEST_URL = os.environ.get('TEST_DATABASE_URL')


@unittest.skipUnless(TEST_URL, 'Set TEST_DATABASE_URL to the dedicated local ocop_leads_test database')
class PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = conninfo_to_dict(TEST_URL)
        if config.get('host') not in ('localhost', '127.0.0.1') or config.get('dbname') != 'ocop_leads_test':
            raise ValueError('Integration tests require local database ocop_leads_test')

    def setUp(self):
        self.env = patch.dict(os.environ, {'DATABASE_URL': TEST_URL, 'LEADS_BACKEND': 'postgres'})
        self.env.start()
        self.addCleanup(self.env.stop)
        with postgres.transaction() as connection:
            connection.execute('DROP SCHEMA IF EXISTS business CASCADE')
        self.addCleanup(self.clean_schema)
        postgres.initialize_schema()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'fake.sqlite3'
        with closing(sqlite3.connect(self.source)) as connection, connection:
            connection.execute('''CREATE TABLE leads (id INTEGER PRIMARY KEY, created_at TEXT,
                kind TEXT, name TEXT, email TEXT, phone TEXT, note TEXT, legacy_duckdb_id INTEGER)''')
            connection.executemany('INSERT INTO leads VALUES (?,?,?,?,?,?,?,?)', [
                (1, '2026-01-01T07:00:00+07:00', 'buyer', 'Test A', 'a@example.com', '0', 'Note', None),
                (2, '2026-01-02T00:00:00+00:00', 'supplier', 'Test B', 'b@example.com', '1', 'Note', 7),
            ])

    def clean_schema(self):
        with postgres.transaction() as connection:
            connection.execute('DROP SCHEMA IF EXISTS business CASCADE')

    def count(self):
        with postgres.transaction() as connection:
            return connection.execute('SELECT count(*) FROM business.leads').fetchone()[0]

    def fail_at_commit(self):
        with postgres.transaction() as connection:
            connection.execute('''CREATE FUNCTION business.reject_commit() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test commit failure'; END $$''')
            connection.execute('''CREATE CONSTRAINT TRIGGER reject_commit AFTER INSERT ON business.leads
                DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION business.reject_commit()''')

    def test_save_commits_and_rollback_at_commit(self):
        import secrets
        password = secrets.token_urlsafe(16)
        accounts.seed_accounts(password)
        session = auth.authenticate('buyer01', password)
        lead_id = leads.save_lead(leads.KINDS['buyer'], ' Test ', 'a@example.com', '0', 'Note', session=session)
        with postgres.transaction() as connection:
            self.assertEqual(connection.execute('SELECT name FROM business.leads WHERE id=%s', (lead_id,)).fetchone(), ('Test',))
        self.fail_at_commit()
        opened = []
        real_connect = psycopg.connect
        def capture_connection(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            opened.append(connection)
            return connection
        with patch('data.sqlite_leads.save_lead', side_effect=AssertionError('No fallback')), \
                patch('psycopg.connect', side_effect=capture_connection):
            with self.assertRaises(leads.LeadStorageError):
                leads.save_lead(leads.KINDS['buyer'], 'Rollback', 'a@example.com', '0', 'Note', session=session)
        self.assertTrue(opened[0].closed)
        self.assertEqual(self.count(), 1)

    def test_transaction_rolls_back_after_insert(self):
        with self.assertRaises(RuntimeError):
            with postgres.transaction() as connection:
                connection.execute("INSERT INTO business.leads(kind,name,email,phone,note) VALUES ('b','t','e','0','n')")
                raise RuntimeError('test')
        self.assertEqual(self.count(), 0)

    def test_import_twice_dry_run_and_source_unchanged(self):
        before = self.source.read_bytes()
        preview = migrate_leads.migrate(self.source, 'fixture', dry_run=True)
        self.assertEqual((preview.would_insert, preview.failed, self.count()), (2, 0, 0))
        first = migrate_leads.migrate(self.source, 'fixture', dry_run=False)
        second = migrate_leads.migrate(self.source, 'fixture', dry_run=False)
        self.assertEqual((first.inserted, first.failed), (2, 0))
        self.assertEqual((second.inserted, second.skipped, second.failed, self.count()), (0, 2, 0, 2))
        self.assertEqual(self.source.read_bytes(), before)
        with postgres.transaction() as connection:
            self.assertEqual(connection.execute('SELECT created_at FROM business.leads WHERE legacy_sqlite_id=1').fetchone()[0].hour, 0)

    def test_invalid_row_rolls_back_savepoint_and_reports_partial_success(self):
        with closing(sqlite3.connect(self.source)) as connection, connection:
            connection.execute("UPDATE leads SET created_at='not-a-time' WHERE id=1")
        result = migrate_leads.migrate(self.source, 'fixture', dry_run=False)
        self.assertEqual((result.inserted, result.failed, self.count()), (1, 1, 1))
        with closing(sqlite3.connect(self.source)) as connection, connection:
            connection.execute("UPDATE leads SET created_at='2026-01-01T00:00:00+00:00' WHERE id=1")
        retry = migrate_leads.migrate(self.source, 'fixture', dry_run=False)
        self.assertEqual((retry.inserted, retry.skipped, retry.failed), (1, 1, 0))

    def test_database_constraint_failure_keeps_valid_rows(self):
        with postgres.transaction() as connection:
            connection.execute("ALTER TABLE business.leads ADD CHECK (name <> 'Test A')")
        result = migrate_leads.migrate(self.source, 'fixture', dry_run=False)
        self.assertEqual((result.inserted, result.failed, self.count()), (1, 1, 1))

    def test_import_commit_failure_reports_zero_committed(self):
        self.fail_at_commit()
        result = migrate_leads.migrate(self.source, 'fixture', dry_run=False)
        self.assertEqual((result.inserted, result.failed, self.count()), (0, 2, 0))
        self.assertIsNotNone(result.error)

    def test_late_commit_failure_rolls_back_earlier_rows(self):
        with postgres.transaction() as connection:
            connection.execute('''CREATE FUNCTION business.reject_second() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                    IF NEW.legacy_sqlite_id = 2 THEN RAISE EXCEPTION 'late failure'; END IF;
                    RETURN NEW; END $$''')
            connection.execute('''CREATE CONSTRAINT TRIGGER reject_second AFTER INSERT ON business.leads
                DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION business.reject_second()''')
        result = migrate_leads.migrate(self.source, 'fixture', dry_run=False)
        self.assertEqual((result.inserted, result.failed, self.count()), (0, 2, 0))

    def test_changed_source_is_conflict_not_silent_skip(self):
        migrate_leads.migrate(self.source, 'fixture', dry_run=False)
        with closing(sqlite3.connect(self.source)) as connection, connection:
            connection.execute("UPDATE leads SET note='Changed' WHERE id=1")
        result = migrate_leads.migrate(self.source, 'fixture', dry_run=False)
        self.assertEqual((result.inserted, result.skipped, result.failed, self.count()), (0, 1, 1, 2))

    def test_separate_sources_can_share_sqlite_ids(self):
        with closing(sqlite3.connect(self.source)) as connection, connection:
            connection.execute('UPDATE leads SET legacy_duckdb_id=NULL')
        for source_id in ('source-a', 'source-b'):
            result = migrate_leads.migrate(self.source, source_id, dry_run=False)
            self.assertEqual((result.inserted, result.failed), (2, 0))
        self.assertEqual(self.count(), 4)

    def test_cli_reports_counts_and_exit_status(self):
        output = io.StringIO()
        with redirect_stdout(output):
            status = migrate_leads.main(['--source', str(self.source), '--source-id', 'fixture', '--apply'])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())['inserted'], 2)
        with closing(sqlite3.connect(self.source)) as connection, connection:
            connection.execute("UPDATE leads SET note='Conflict' WHERE id=1")
        output = io.StringIO()
        with redirect_stdout(output):
            status = migrate_leads.main(['--source', str(self.source), '--source-id', 'fixture', '--apply'])
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output.getvalue())['failed'], 1)

    def test_migrations_repeatable_and_upgrade_prepared_schema(self):
        postgres.initialize_schema()
        with postgres.transaction() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM business.schema_migrations').fetchone()[0], 4)
            connection.execute('DROP SCHEMA business CASCADE')
            connection.execute(Path('data/migrations/001_create_leads.sql').read_text(encoding='utf-8'))
            connection.execute("INSERT INTO business.leads(kind,name,email,phone,note,legacy_sqlite_id) VALUES ('b','old','e','0','n',8)")
        postgres.initialize_schema()
        with postgres.transaction() as connection:
            self.assertEqual(connection.execute('SELECT legacy_sqlite_source FROM business.leads').fetchone()[0], 'legacy-default')
            self.assertEqual(connection.execute('SELECT name,note,user_id FROM business.leads').fetchone(), ('old', 'n', None))

