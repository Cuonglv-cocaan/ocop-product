import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch
from uuid import uuid4

from data import auth, chat


class ChatStorageTests(unittest.TestCase):
    def setUp(self):
        self.connection = Mock()
        @contextmanager
        def transaction():
            yield self.connection
        tx = patch('data.chat.postgres.transaction', transaction)
        actor = patch('data.chat.auth.require_user', return_value={'id': 7})
        tx.start()
        actor.start()
        self.addCleanup(tx.stop)
        self.addCleanup(actor.stop)

    def test_guest_insert_has_no_user_and_has_session_key(self):
        cid, key = uuid4(), uuid4()
        self.connection.execute.return_value.fetchone.return_value = (1,)
        with patch('data.chat.auth.require_user') as require_user:
            result = chat.save_conversation(None, cid, [{'role': 'user', 'content': 'Tea'}], session_key=key)
        self.assertEqual(result, 1)
        require_user.assert_not_called()
        params = self.connection.execute.call_args_list[0].args[1]
        self.assertEqual(params[:2], (cid, None))
        self.assertEqual(params[-1], key)
        turn_params = self.connection.execute.call_args_list[1].args[1]
        self.assertEqual(turn_params[:4], (cid, 1, 'Tea', None))
        self.assertEqual(turn_params[-2], 'pending')

    def test_multiple_questions_create_separate_turn_rows(self):
        cid = uuid4()
        self.connection.execute.return_value.fetchone.return_value = (3,)
        messages = [
            {'role': 'user', 'content': 'Tea'},
            {'role': 'assistant', 'content': 'Green tea', 'products': [{'product_id': 'tea'}],
             'followup_questions': ['Compare tea?', 'Cheaper tea?']},
            {'role': 'user', 'content': 'Cheaper?'},
            {'role': 'assistant', 'content': 'Unavailable', 'error': True},
            {'role': 'user', 'content': 'Coffee?'},
        ]
        chat.save_conversation(None, cid, messages, 2, session_key=uuid4())
        calls = self.connection.execute.call_args_list
        self.assertEqual(len(calls), 4)  # Metadata plus one row per question.
        self.assertNotIn('SET messages=', calls[0].args[0])
        self.assertEqual([c.args[1][1] for c in calls[1:]], [1, 2, 3])
        self.assertEqual([c.args[1][2] for c in calls[1:]], ['Tea', 'Cheaper?', 'Coffee?'])
        self.assertEqual([c.args[1][-2] for c in calls[1:]], ['answered', 'error', 'pending'])
        self.assertEqual(calls[1].args[1][4].obj, [{'product_id': 'tea'}])
        self.assertEqual(calls[1].args[1][5].obj, ['Compare tea?', 'Cheaper tea?'])
        self.assertEqual(calls[2].args[1][5].obj, [])

    def test_answer_updates_the_same_question_on_retry(self):
        cid, key = uuid4(), uuid4()
        self.connection.execute.return_value.fetchone.return_value = (1,)
        messages = [{'role': 'user', 'content': 'Tea'}]
        chat.save_conversation(None, cid, messages, session_key=key)
        first = self.connection.execute.call_args.args[1]
        messages.append({'role': 'assistant', 'content': 'Green tea'})
        chat.save_conversation(None, cid, messages, 1, session_key=key)
        sql, completed = self.connection.execute.call_args.args
        self.assertEqual(first[:3], completed[:3])
        self.assertEqual(completed[3], 'Green tea')
        self.assertIn('ON CONFLICT (conversation_id,turn_number) DO UPDATE', sql)

    def test_stale_revision_cannot_overwrite(self):
        self.connection.execute.return_value.fetchone.return_value = None
        with self.assertRaises(ValueError):
            chat.save_conversation(object(), uuid4(), [{'role': 'user', 'content': 'Trà'}], 3,
                                   session_key=uuid4())
        sql, params = self.connection.execute.call_args.args
        self.assertIn('user_id IS NOT DISTINCT FROM %s AND session_key=%s AND revision=%s', sql)
        self.assertEqual(params[-3], 7)
        self.assertEqual(params[-1], 3)

    def test_invalid_login_cannot_fall_back_to_guest_write(self):
        with patch('data.chat.auth.require_user', side_effect=auth.AccessDenied('Denied')):
            with self.assertRaises(auth.AccessDenied):
                chat.save_conversation(object(), uuid4(), [{'role': 'user', 'content': 'Tea'}],
                                       session_key=uuid4())
        self.connection.execute.assert_not_called()
