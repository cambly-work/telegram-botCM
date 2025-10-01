CREATE TABLE IF NOT EXISTS weekly_keys (
    id              SERIAL PRIMARY KEY,
    week            INT NOT NULL UNIQUE,
    status          TEXT NOT NULL DEFAULT 'inactive' CHECK (status IN ('inactive', 'active')),
    title           TEXT,
    key_description TEXT,
    bonus_description TEXT,
    bonus_link      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_weekly_keys_status ON weekly_keys(status);

CREATE TABLE IF NOT EXISTS user_keys (
    id             SERIAL PRIMARY KEY,
    user_id        INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    weekly_key_id  INT NOT NULL REFERENCES weekly_keys(id) ON DELETE CASCADE,
    week           INT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'claimed', 'revoked')),
    bonus_link     TEXT,
    granted_by     BIGINT,
    granted_at     TIMESTAMPTZ DEFAULT NOW(),
    claimed_at     TIMESTAMPTZ,
    revoked_by     BIGINT,
    revoked_at     TIMESTAMPTZ,
    UNIQUE (user_id, weekly_key_id)
);

CREATE INDEX IF NOT EXISTS idx_user_keys_user ON user_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_user_keys_week ON user_keys(week);
CREATE INDEX IF NOT EXISTS idx_user_keys_status ON user_keys(status);
