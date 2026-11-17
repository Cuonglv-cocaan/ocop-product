ALTER TABLE business.chat_turns ADD COLUMN followup_questions JSONB NOT NULL
    DEFAULT '[]'::jsonb CHECK (jsonb_typeof(followup_questions) = 'array');

-- Preserve existing view column order and append the new research field.
CREATE OR REPLACE VIEW business.chat_research AS
SELECT t.id,t.conversation_id,t.turn_number,t.question,t.answer,t.products,t.status,
       t.asked_at,t.answered_at,c.user_id,c.session_key,c.title AS conversation_title,
       t.followup_questions
FROM business.chat_turns t
JOIN business.chat_conversations c ON c.id=t.conversation_id;
