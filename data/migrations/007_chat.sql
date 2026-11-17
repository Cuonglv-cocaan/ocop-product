CREATE TABLE business.chat_conversations (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES business.users(id),
    title TEXT NOT NULL,
    messages JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(messages) = 'array'),
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX chat_conversations_owner_idx
    ON business.chat_conversations(user_id, updated_at DESC);
REVOKE ALL ON business.chat_conversations FROM PUBLIC;
