-- Retain research data; new chats belong to a temporary UI session.
ALTER TABLE business.chat_conversations ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE business.chat_conversations ADD COLUMN session_key UUID;
CREATE INDEX chat_conversations_session_idx ON business.chat_conversations(session_key);
