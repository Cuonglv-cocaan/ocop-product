"""One research record per question, scoped to a temporary server session."""
import json
from uuid import UUID

from psycopg.types.json import Jsonb
from . import auth, postgres


def conversation_turns(messages):
    turns = []
    for message in messages:
        if message['role'] == 'user':
            turns.append({'question': message['content'], 'answer': None,
                          'products': [], 'followup_questions': [], 'status': 'pending'})
        elif not turns or turns[-1]['status'] != 'pending':
            raise ValueError('Thứ tự tin nhắn không hợp lệ.')
        else:
            turns[-1].update(answer=message['content'], products=message.get('products', []),
                             followup_questions=message.get('followup_questions', []),
                             status='error' if message.get('error') else 'answered')
    return turns


def save_conversation(session, conversation_id, messages, revision=0, *, session_key):
    if not messages or len(json.dumps(messages, ensure_ascii=False)) > 2_000_000:
        raise ValueError('Hội thoại trống hoặc quá dài. Hãy bắt đầu hội thoại mới.')
    if any(m.get('role') not in ('user', 'assistant') or not isinstance(m.get('content'), str)
           for m in messages):
        raise ValueError('Tin nhắn không hợp lệ.')
    title = next((m['content'][:80] for m in messages if m['role'] == 'user'), 'Hội thoại')
    turns = conversation_turns(messages)
    with postgres.transaction() as connection:
        user_id = auth.require_user(connection, session)['id'] if session is not None else None
        params = (UUID(str(conversation_id)), user_id)
        session_key = UUID(str(session_key))
        if revision == 0:
            row = connection.execute('''INSERT INTO business.chat_conversations
                (id,user_id,title,session_key) VALUES (%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING RETURNING revision''',
                (*params, title, session_key)).fetchone()
        else:
            row = connection.execute('''UPDATE business.chat_conversations
                SET revision=revision+1,updated_at=CURRENT_TIMESTAMP
                WHERE id=%s AND user_id IS NOT DISTINCT FROM %s AND session_key=%s AND revision=%s RETURNING revision''',
                (*params, session_key, revision)).fetchone()
        if row is None:
            raise ValueError('Chưa thể lưu hội thoại. Hãy thử lưu lại.')
        for number, turn in enumerate(turns, 1):
            connection.execute('''INSERT INTO business.chat_turns
                (conversation_id,turn_number,question,answer,products,followup_questions,status,answered_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,
                    CASE WHEN %s = 'pending' THEN NULL ELSE CURRENT_TIMESTAMP END)
                ON CONFLICT (conversation_id,turn_number) DO UPDATE
                SET answer=EXCLUDED.answer,products=EXCLUDED.products,status=EXCLUDED.status,
                    followup_questions=EXCLUDED.followup_questions,
                    answered_at=CASE WHEN chat_turns.answer IS DISTINCT FROM EXCLUDED.answer
                        OR chat_turns.status IS DISTINCT FROM EXCLUDED.status
                        THEN EXCLUDED.answered_at ELSE chat_turns.answered_at END
                WHERE (chat_turns.answer,chat_turns.products,chat_turns.status,chat_turns.followup_questions)
                    IS DISTINCT FROM (EXCLUDED.answer,EXCLUDED.products,EXCLUDED.status,EXCLUDED.followup_questions)''',
                (params[0], number, turn['question'], turn['answer'], Jsonb(turn['products']),
                 Jsonb(turn['followup_questions']), turn['status'], turn['status']))
        return row[0]
