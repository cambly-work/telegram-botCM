BEGIN;

-- Drop legacy unique index referencing the old slug column if it still exists.
DROP INDEX IF EXISTS ux_form_sessions_user_slug;

-- Rename slug column to form_slug when needed.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'form_sessions'
          AND column_name = 'slug'
    ) THEN
        EXECUTE 'ALTER TABLE form_sessions RENAME COLUMN slug TO form_slug';
    END IF;
END
$$;

-- Ensure the new reminder columns are present.
ALTER TABLE form_sessions
    ADD COLUMN IF NOT EXISTS last_reminder_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reminder_count INT;

-- Normalise reminder_count values and enforce default/not-null semantics.
UPDATE form_sessions
SET reminder_count = 0
WHERE reminder_count IS NULL;

ALTER TABLE form_sessions
    ALTER COLUMN reminder_count SET DEFAULT 0;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'form_sessions'
          AND column_name = 'reminder_count'
    ) THEN
        BEGIN
            EXECUTE 'ALTER TABLE form_sessions ALTER COLUMN reminder_count SET NOT NULL';
        EXCEPTION WHEN others THEN
            -- Ignore if column cannot be set NOT NULL (e.g. concurrent NULL insertions).
            NULL;
        END;
    END IF;
END
$$;

-- Align started_at with the desired defaults/constraints.
UPDATE form_sessions
SET started_at = NOW()
WHERE started_at IS NULL;

ALTER TABLE form_sessions
    ALTER COLUMN started_at SET DEFAULT NOW();

DO $$
BEGIN
    BEGIN
        EXECUTE 'ALTER TABLE form_sessions ALTER COLUMN started_at SET NOT NULL';
    EXCEPTION WHEN others THEN
        NULL;
    END;
END
$$;

-- Re-create the unique index using the new column name.
CREATE UNIQUE INDEX IF NOT EXISTS ux_form_sessions_user_form_slug
    ON form_sessions(user_id, form_slug);

-- Helpful secondary indexes for reminder queries.
CREATE INDEX IF NOT EXISTS idx_form_sessions_completed
    ON form_sessions(completed_at);

CREATE INDEX IF NOT EXISTS idx_form_sessions_user_started
    ON form_sessions(user_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_form_sessions_incomplete
    ON form_sessions(completed_at, started_at);

COMMIT;
