import json
import unittest
from unittest.mock import MagicMock, patch

from data import purchase


class UnassignTests(unittest.TestCase):
    def test_database_quote_check_blocks_stale_ui(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = (1,)
        with patch('data.purchase.postgres.transaction') as transaction, \
                patch('data.purchase.auth.require_user', return_value={'id': 1}) as authorize, \
                patch('data.purchase._request', return_value={'status': 'quoted'}), \
                patch('data.purchase._cursor') as cursor, \
                patch('data.purchase._event') as event:
            transaction.return_value.__enter__.return_value = connection
            cursor.return_value.execute.return_value.fetchone.return_value = {'id': 7, 'supplier_name': 'Unit'}
            with self.assertRaisesRegex(ValueError, 'báo giá'):
                purchase.unassign_supplier('session', 3, 7)
            authorize.assert_called_once_with(connection, 'session', {'admin'})
            event.assert_not_called()
            self.assertFalse(any('DELETE' in call.args[0] for call in connection.execute.call_args_list))

    def test_cancellation_archives_snapshot_before_removing_access(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = None
        match = {'id': 7, 'supplier_name': 'Unit', 'matching_snapshot': {'score': 90}}
        with patch('data.purchase.postgres.transaction') as transaction, \
                patch('data.purchase.auth.require_user', return_value={'id': 1}), \
                patch('data.purchase._request', return_value={'status': 'assigned'}), \
                patch('data.purchase._cursor') as cursor, \
                patch('data.purchase._event') as event:
            transaction.return_value.__enter__.return_value = connection
            cursor.return_value.execute.return_value.fetchone.return_value = match
            purchase.unassign_supplier('session', 3, 7)
            self.assertEqual(event.call_args.args[3], 'unassigned')
            self.assertEqual(json.loads(event.call_args.args[4])['assignment'], match)
            statements = [call.args[0] for call in connection.execute.call_args_list]
            self.assertIn('SET match_id=NULL', statements[1])
            self.assertIn('DELETE FROM business.request_matches', statements[2])
            self.assertIn("ELSE 'open'", statements[3])


if __name__ == '__main__':
    unittest.main()
