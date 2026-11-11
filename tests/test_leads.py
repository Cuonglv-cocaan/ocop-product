import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg

from data import leads, postgres, sqlite_leads


class LeadTests(unittest.TestCase):
    def test_sqlite_default_even_with_database_url(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(sqlite_leads, 'SQLITE_LEADS_PATH', Path(directory) / 'leads.sqlite3'), \
                patch.dict(os.environ, {'LEADS_BACKEND': 'sqlite', 'DATABASE_URL': 'unused'}), \
                patch('psycopg.connect', side_effect=AssertionError('No PostgreSQL')):
            lead_id = leads.save_lead('buyer', ' Name ', 'a@b.co', '0', ' Note ')
            with closing(sqlite_leads.connect_leads()) as connection:
                self.assertEqual(connection.execute('SELECT name,note FROM leads WHERE id=?', [lead_id]).fetchone(), ('Name', 'Note'))

    def test_secrets_and_environment_precedence(self):
        with patch.dict(os.environ, {}, clear=True), patch('streamlit.secrets', {'DATABASE_URL': 'secret'}):
            self.assertEqual(postgres.setting('DATABASE_URL'), 'secret')
            with patch.dict(os.environ, {'DATABASE_URL': 'environment'}):
                self.assertEqual(postgres.setting('DATABASE_URL'), 'environment')

    def test_postgres_parameterized_insert_and_connection_context(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.fetchone.return_value = (42,)
        with patch.dict(os.environ, {'LEADS_BACKEND': 'postgres', 'DATABASE_URL': 'postgresql://example'}), \
                patch('psycopg.connect', return_value=connection) as connect, \
                patch.object(sqlite_leads, 'connect_leads', side_effect=AssertionError('No fallback')):
            self.assertEqual(leads.save_lead('buyer', " O'Name ", 'a@b.co', '0', ' Note '), 42)
        connect.assert_called_once_with('postgresql://example', connect_timeout=10, prepare_threshold=None)
        args = connection.execute.call_args.args
        self.assertIn('RETURNING id', args[0])
        self.assertEqual(args[1], ('buyer', "O'Name", 'a@b.co', '0', 'Note'))
        connection.__exit__.assert_called_once_with(None, None, None)

    def test_postgres_failure_enters_rollback_context_and_redacts(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.side_effect = psycopg.OperationalError('private-url')
        with patch.dict(os.environ, {'LEADS_BACKEND': 'postgres', 'DATABASE_URL': 'private-url'}), \
                patch('psycopg.connect', return_value=connection), \
                patch.object(sqlite_leads, 'save_lead', side_effect=AssertionError('No fallback')):
            with self.assertRaises(leads.LeadStorageError) as error:
                leads.save_lead('buyer', 'Name', 'a@b.co', '0', 'Note')
        self.assertNotIn('private-url', str(error.exception))
        self.assertIs(connection.__exit__.call_args.args[0], psycopg.OperationalError)

    def test_missing_url_and_invalid_backend_do_not_connect(self):
        for config in ({'LEADS_BACKEND': 'postgres', 'DATABASE_URL': ''},
                       {'LEADS_BACKEND': '', 'DATABASE_URL': ''},
                       {'LEADS_BACKEND': 'typo', 'DATABASE_URL': ''}):
            with self.subTest(config=config), patch.dict(os.environ, config), patch('psycopg.connect') as connect:
                with self.assertRaises(leads.LeadStorageError):
                    leads.save_lead('buyer', 'Name', 'a@b.co', '0', 'Note')
                connect.assert_not_called()

    def test_commit_failure_does_not_return_success(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.fetchone.return_value = (42,)
        connection.__exit__.side_effect = psycopg.OperationalError('commit failed')
        with patch.dict(os.environ, {'LEADS_BACKEND': 'postgres', 'DATABASE_URL': 'test'}), \
                patch('psycopg.connect', return_value=connection), \
                patch.object(sqlite_leads, 'save_lead', side_effect=AssertionError('No fallback')):
            with self.assertRaises(leads.LeadStorageError):
                leads.save_lead('buyer', 'Name', 'a@b.co', '0', 'Note')
        connection.close.assert_called_once()
