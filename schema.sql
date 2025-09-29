-- =========================
-- SCHEMA v3.1 (compatible with handlers.py)
-- =========================

-- USERS
CREATE TABLE IF NOT EXISTS users (
  id                 SERIAL PRIMARY KEY,
  tg_user_id         BIGINT NOT NULL UNIQUE,
  username           TEXT,
  full_name          TEXT,
  name               TEXT,
  email              TEXT,
  phone              TEXT,
  at_user_id         TEXT,
  utm_source         TEXT,
  utm_medium         TEXT,
  utm_campaign       TEXT,
  status             TEXT CHECK (status IN ('lead_funnel','member_active','member_expired'))
                     DEFAULT 'lead_funnel',
  access_until       TIMESTAMPTZ,
  joined_club_at     TIMESTAMPTZ,
  last_activity_at   TIMESTAMPTZ,
  funnel_complete    BOOLEAN DEFAULT FALSE,
  requested_session  BOOLEAN DEFAULT FALSE,
  created_at         TIMESTAMPTZ DEFAULT NOW(),
  updated_at         TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS full_name          TEXT,
  ADD COLUMN IF NOT EXISTS name               TEXT,
  ADD COLUMN IF NOT EXISTS email              TEXT,
  ADD COLUMN IF NOT EXISTS phone              TEXT,
  ADD COLUMN IF NOT EXISTS at_user_id         TEXT,
  ADD COLUMN IF NOT EXISTS utm_source         TEXT,
  ADD COLUMN IF NOT EXISTS utm_medium         TEXT,
  ADD COLUMN IF NOT EXISTS utm_campaign       TEXT,
  ADD COLUMN IF NOT EXISTS status             TEXT DEFAULT 'lead_funnel',
  ADD COLUMN IF NOT EXISTS access_until       TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS joined_club_at     TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_activity_at   TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS funnel_complete    BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS requested_session  BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS created_at         TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS updated_at         TIMESTAMPTZ DEFAULT NOW();

ALTER TABLE users
  ALTER COLUMN access_until TYPE TIMESTAMPTZ
    USING CASE
      WHEN pg_typeof(access_until) = 'timestamp without time zone'::regtype
        THEN timezone('UTC', access_until)
      ELSE access_until
    END;

DO $$
BEGIN
  BEGIN
    ALTER TABLE users
      ADD CONSTRAINT users_status_check
      CHECK (status IN ('lead_funnel','member_active','member_expired'));
  EXCEPTION WHEN duplicate_object THEN
    NULL;
  END;
END$$;

CREATE INDEX IF NOT EXISTS idx_users_username         ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_status           ON users(status);
CREATE INDEX IF NOT EXISTS idx_users_access_until     ON users(access_until);
CREATE INDEX IF NOT EXISTS idx_users_last_activity    ON users(last_activity_at);
CREATE INDEX IF NOT EXISTS idx_users_status_access    ON users(status, access_until);

CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email_nonnull
  ON users(LOWER(email))
  WHERE email IS NOT NULL AND email <> '';

CREATE UNIQUE INDEX IF NOT EXISTS ux_users_phone_nonnull
  ON users(phone)
  WHERE phone IS NOT NULL AND phone <> '';

-- FUNNEL_PROGRESS
CREATE TABLE IF NOT EXISTS funnel_progress (
  id            SERIAL PRIMARY KEY,
  user_id       INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  lesson_num    INT CHECK (lesson_num BETWEEN 1 AND 4) NOT NULL,
  delivered_at  TIMESTAMPTZ,
  opened_at     TIMESTAMPTZ,
  hw_answer     TEXT,
  hw_status     TEXT CHECK (hw_status IN ('submitted','skipped','pending')) DEFAULT 'pending'
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_funnel_user_lesson ON funnel_progress(user_id, lesson_num);
CREATE INDEX IF NOT EXISTS idx_funnel_user              ON funnel_progress(user_id);
CREATE INDEX IF NOT EXISTS idx_funnel_status_opened     ON funnel_progress(hw_status, opened_at);
CREATE INDEX IF NOT EXISTS idx_funnel_delivered_at      ON funnel_progress(delivered_at);

-- LESSON_FEEDBACK
CREATE TABLE IF NOT EXISTS lesson_feedback (
  id            SERIAL PRIMARY KEY,
  user_id       INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  lesson_num    INT NOT NULL,
  feedback_type TEXT NOT NULL,
  feedback_text TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_feedback_user ON lesson_feedback(user_id);

-- PAYMENTS (опционально, совместимость)
CREATE TABLE IF NOT EXISTS payments (
  id            SERIAL PRIMARY KEY,
  order_id      TEXT,
  at_user_id    TEXT,
  email         TEXT,
  phone         TEXT,
  product_id    TEXT,
  status        TEXT CHECK (status IN ('paid','renew','refund','failed')),
  paid_at       TIMESTAMPTZ,
  access_until  TIMESTAMPTZ,
  raw_payload   JSONB,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE payments
  ALTER COLUMN access_until TYPE TIMESTAMPTZ
    USING CASE
      WHEN pg_typeof(access_until) = 'timestamp without time zone'::regtype
        THEN timezone('UTC', access_until)
      ELSE access_until
    END;
CREATE UNIQUE INDEX IF NOT EXISTS ux_payments_order_id ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_status         ON payments(status);
CREATE INDEX IF NOT EXISTS idx_payments_email          ON payments(LOWER(email));
CREATE INDEX IF NOT EXISTS idx_payments_phone          ON payments(phone);

-- CONTENT
CREATE TABLE IF NOT EXISTS content (
  id         SERIAL PRIMARY KEY,
  key        TEXT UNIQUE NOT NULL,
  value      TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_content_key ON content(key);

-- FORM_SESSIONS
CREATE TABLE IF NOT EXISTS form_sessions (
  id               SERIAL PRIMARY KEY,
  user_id          INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  form_slug        TEXT NOT NULL,
  started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at     TIMESTAMPTZ,
  last_reminder_at TIMESTAMPTZ,
  reminder_count   INT NOT NULL DEFAULT 0
);

-- Legacy compatibility: remove the old index and rename slug → form_slug when needed.
DROP INDEX IF EXISTS ux_form_sessions_user_slug;

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

CREATE UNIQUE INDEX IF NOT EXISTS ux_form_sessions_user_form_slug
  ON form_sessions(user_id, form_slug);
CREATE INDEX IF NOT EXISTS idx_form_sessions_completed
  ON form_sessions(completed_at);
CREATE INDEX IF NOT EXISTS idx_form_sessions_user_started
  ON form_sessions(user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_form_sessions_incomplete
  ON form_sessions(completed_at, started_at);

-- TEST_REQUESTS
CREATE TABLE IF NOT EXISTS test_requests (
  id             SERIAL PRIMARY KEY,
  tg_user_id     BIGINT NOT NULL UNIQUE,
  user_id        INT REFERENCES users(id) ON DELETE SET NULL,
  birthdate      DATE NOT NULL,
  preferred_name TEXT,
  status         TEXT NOT NULL DEFAULT 'waiting',
  created_at     TIMESTAMPTZ DEFAULT NOW(),
  updated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_test_requests_status ON test_requests(status);

-- BROADCAST_TEMPLATES
CREATE TABLE IF NOT EXISTS broadcast_templates (
  id         SERIAL PRIMARY KEY,
  slug       TEXT UNIQUE NOT NULL,
  title      TEXT UNIQUE NOT NULL,
  segment    TEXT NOT NULL DEFAULT 'all',
  body       TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_broadcast_templates_segment ON broadcast_templates(segment);

-- ADMIN_LOG (совместимость с v2 → v3)

-- v2 могла уже создать admin_log с (event, user_id, payload, created_at)
CREATE TABLE IF NOT EXISTS admin_log (
  id         SERIAL PRIMARY KEY,
  event      TEXT,
  user_id    INT,
  payload    JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 1) Сначала добавляем нужные колонки для текущих хендлеров
ALTER TABLE admin_log
  ADD COLUMN IF NOT EXISTS admin_id  BIGINT,
  ADD COLUMN IF NOT EXISTS action    TEXT,
  ADD COLUMN IF NOT EXISTS payload   JSONB,
  ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at::timestamptz;

-- 2) Мягко перенесём старые значения event → action (только если action пуст)
UPDATE admin_log
SET action = event
WHERE action IS NULL AND event IS NOT NULL;

-- 3) Теперь индексы (после того, как колонка 'action' гарантированно есть)
CREATE INDEX IF NOT EXISTS idx_admin_log_action ON admin_log(action);
CREATE INDEX IF NOT EXISTS idx_admin_log_event  ON admin_log(event);

-- =========================
-- Конец schema.sql v3.1
-- =========================
