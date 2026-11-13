-- Internal demo accounts only. Never infer ownership of existing leads.
CREATE TABLE business.users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
    role TEXT NOT NULL CHECK (role IN ('buyer', 'seller', 'admin')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    auth_version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (username = lower(trim(username)) AND username ~ '^[a-z0-9_]{3,32}$')
);
ALTER TABLE business.leads ADD COLUMN user_id BIGINT REFERENCES business.users(id);
CREATE INDEX leads_user_id_idx ON business.leads(user_id);
REVOKE ALL ON business.users FROM PUBLIC;
