CREATE TABLE IF NOT EXISTS content_versions (
    id         SERIAL PRIMARY KEY,
    key        TEXT NOT NULL,
    value      TEXT,
    updated_by BIGINT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_content_versions_key_updated
    ON content_versions(key, updated_at DESC);
