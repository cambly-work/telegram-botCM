-- Create analysis_requests table for storing consultation requests
CREATE TABLE IF NOT EXISTS analysis_requests (
    id               SERIAL PRIMARY KEY,
    tg_user_id       BIGINT NOT NULL,
    user_id          INT REFERENCES users(id) ON DELETE SET NULL,
    preferred_format TEXT NOT NULL,
    contact          TEXT NOT NULL,
    preferred_time   TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'new',
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analysis_requests_created_at
    ON analysis_requests(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_requests_status
    ON analysis_requests(status);
CREATE INDEX IF NOT EXISTS idx_analysis_requests_user
    ON analysis_requests(user_id);
