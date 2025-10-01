-- 2024-09-14: indexes for admin form stats aggregation
CREATE INDEX IF NOT EXISTS idx_form_sessions_slug
    ON form_sessions(form_slug);

CREATE INDEX IF NOT EXISTS idx_form_sessions_slug_completed
    ON form_sessions(form_slug, completed_at);
