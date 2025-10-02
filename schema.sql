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

-- CONTENT_VERSIONS
CREATE TABLE IF NOT EXISTS content_versions (
  id         SERIAL PRIMARY KEY,
  key        TEXT NOT NULL,
  value      TEXT,
  updated_by BIGINT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_content_versions_key_updated
  ON content_versions(key, updated_at DESC);

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

ALTER TABLE form_sessions
  ADD COLUMN IF NOT EXISTS last_reminder_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS reminder_count INT;

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
          NULL;
      END;
  END IF;
END
$$;

-- SCHEDULE CYCLE WEEKS
CREATE TABLE IF NOT EXISTS schedule_cycle_weeks (
  id           SERIAL PRIMARY KEY,
  week_number  INT NOT NULL,
  title        TEXT NOT NULL,
  start_date   DATE,
  end_date     DATE,
  is_archived  BOOLEAN NOT NULL DEFAULT FALSE,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE schedule_cycle_weeks
  ADD COLUMN IF NOT EXISTS week_number INT,
  ADD COLUMN IF NOT EXISTS title TEXT,
  ADD COLUMN IF NOT EXISTS start_date DATE,
  ADD COLUMN IF NOT EXISTS end_date DATE,
  ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

DO $$
BEGIN
  IF to_regclass('public.schedule_cycle_weeks_week_number_unique') IS NULL THEN
    ALTER TABLE schedule_cycle_weeks
      ADD CONSTRAINT schedule_cycle_weeks_week_number_unique UNIQUE (week_number);
  END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_schedule_cycle_weeks_active
  ON schedule_cycle_weeks(is_archived, start_date NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_schedule_cycle_weeks_dates
  ON schedule_cycle_weeks(start_date, end_date);

-- SCHEDULE EVENTS
CREATE TABLE IF NOT EXISTS schedule_events (
  id           SERIAL PRIMARY KEY,
  week_id      INT REFERENCES schedule_cycle_weeks(id) ON DELETE SET NULL,
  scheduled_at TIMESTAMPTZ NOT NULL,
  event_type   TEXT NOT NULL,
  description  TEXT,
  link         TEXT,
  is_archived  BOOLEAN NOT NULL DEFAULT FALSE,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE schedule_events
  ADD COLUMN IF NOT EXISTS week_id INT,
  ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS event_type TEXT,
  ADD COLUMN IF NOT EXISTS description TEXT,
  ADD COLUMN IF NOT EXISTS link TEXT,
  ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_schedule_events_active
  ON schedule_events(is_archived, scheduled_at);

CREATE INDEX IF NOT EXISTS idx_schedule_events_week
  ON schedule_events(week_id);

-- SCHEDULE EVENT REMINDERS
CREATE TABLE IF NOT EXISTS schedule_event_reminders (
  id           SERIAL PRIMARY KEY,
  event_id     INT NOT NULL REFERENCES schedule_events(id) ON DELETE CASCADE,
  user_id      INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  remind_at    TIMESTAMPTZ NOT NULL,
  notified_at  TIMESTAMPTZ,
  is_cancelled BOOLEAN NOT NULL DEFAULT FALSE,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(event_id, user_id)
);

ALTER TABLE schedule_event_reminders
  ADD COLUMN IF NOT EXISTS event_id INT,
  ADD COLUMN IF NOT EXISTS user_id INT,
  ADD COLUMN IF NOT EXISTS remind_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS notified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS is_cancelled BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_schedule_event_reminders_due
  ON schedule_event_reminders(remind_at)
  WHERE is_cancelled = FALSE AND notified_at IS NULL;

-- WEEKLY_KEYS
CREATE TABLE IF NOT EXISTS weekly_keys (
  id                SERIAL PRIMARY KEY,
  week              INT NOT NULL UNIQUE,
  status            TEXT NOT NULL DEFAULT 'inactive' CHECK (status IN ('inactive','active')),
  title             TEXT,
  key_description   TEXT,
  bonus_description TEXT,
  bonus_link        TEXT,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE weekly_keys
  ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'inactive',
  ADD COLUMN IF NOT EXISTS title TEXT,
  ADD COLUMN IF NOT EXISTS key_description TEXT,
  ADD COLUMN IF NOT EXISTS bonus_description TEXT,
  ADD COLUMN IF NOT EXISTS bonus_link TEXT,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

DO $$
BEGIN
  BEGIN
    EXECUTE $wk$ALTER TABLE weekly_keys
      ADD CONSTRAINT weekly_keys_status_check
      CHECK (status IN ('inactive','active'))$wk$;
  EXCEPTION WHEN duplicate_object THEN
    NULL;
  END;
END$$;

CREATE INDEX IF NOT EXISTS idx_weekly_keys_status ON weekly_keys(status);

-- USER_KEYS
CREATE TABLE IF NOT EXISTS user_keys (
  id             SERIAL PRIMARY KEY,
  user_id        INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  weekly_key_id  INT NOT NULL REFERENCES weekly_keys(id) ON DELETE CASCADE,
  week           INT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available','claimed','revoked')),
  bonus_link     TEXT,
  granted_by     BIGINT,
  granted_at     TIMESTAMPTZ DEFAULT NOW(),
  claimed_at     TIMESTAMPTZ,
  revoked_by     BIGINT,
  revoked_at     TIMESTAMPTZ,
  UNIQUE (user_id, weekly_key_id)
);

ALTER TABLE user_keys
  ADD COLUMN IF NOT EXISTS weekly_key_id INT REFERENCES weekly_keys(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS week INT,
  ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'available',
  ADD COLUMN IF NOT EXISTS bonus_link TEXT,
  ADD COLUMN IF NOT EXISTS granted_by BIGINT,
  ADD COLUMN IF NOT EXISTS granted_at TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS revoked_by BIGINT,
  ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ;

DO $$
BEGIN
  BEGIN
    EXECUTE $uk$ALTER TABLE user_keys
      ADD CONSTRAINT user_keys_status_check
      CHECK (status IN ('available','claimed','revoked'))$uk$;
  EXCEPTION WHEN duplicate_object THEN
    NULL;
  END;
END$$;

CREATE INDEX IF NOT EXISTS idx_user_keys_user ON user_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_user_keys_week ON user_keys(week);
CREATE INDEX IF NOT EXISTS idx_user_keys_status ON user_keys(status);

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
CREATE INDEX IF NOT EXISTS idx_form_sessions_slug
  ON form_sessions(form_slug);
CREATE INDEX IF NOT EXISTS idx_form_sessions_slug_completed
  ON form_sessions(form_slug, completed_at);

-- ANALYSIS_REQUESTS
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
  placeholders JSONB NOT NULL DEFAULT '[]'::jsonb,
  cta_description TEXT,
  cta_buttons JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_broadcast_templates_segment ON broadcast_templates(segment);

ALTER TABLE broadcast_templates
  ADD COLUMN IF NOT EXISTS placeholders JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS cta_description TEXT,
  ADD COLUMN IF NOT EXISTS cta_buttons JSONB;

UPDATE broadcast_templates
  SET placeholders = '[]'::jsonb
  WHERE placeholders IS NULL;

ALTER TABLE broadcast_templates
  ALTER COLUMN placeholders SET DEFAULT '[]'::jsonb,
  ALTER COLUMN placeholders SET NOT NULL;

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
  ADD COLUMN IF NOT EXISTS admin_id  BIGINT;

ALTER TABLE admin_log
  ADD COLUMN IF NOT EXISTS action    TEXT;

ALTER TABLE admin_log
  ADD COLUMN IF NOT EXISTS payload   JSONB;

ALTER TABLE admin_log
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

-- MATERIAL_CATEGORIES
CREATE TABLE IF NOT EXISTS material_categories (
  id              SERIAL PRIMARY KEY,
  slug            TEXT NOT NULL UNIQUE,
  title           TEXT NOT NULL,
  content_key     TEXT NOT NULL UNIQUE,
  parent_id       INT REFERENCES material_categories(id) ON DELETE CASCADE,
  requires_access BOOLEAN NOT NULL DEFAULT TRUE,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order      INT NOT NULL DEFAULT 100,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_material_categories_parent
  ON material_categories(parent_id);

CREATE TABLE IF NOT EXISTS material_category_access (
  id          SERIAL PRIMARY KEY,
  category_id INT NOT NULL REFERENCES material_categories(id) ON DELETE CASCADE,
  user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  granted_by  BIGINT,
  granted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at  TIMESTAMPTZ,
  UNIQUE (category_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_material_category_access_user
  ON material_category_access(user_id);

CREATE INDEX IF NOT EXISTS idx_material_category_access_category
  ON material_category_access(category_id);

INSERT INTO material_categories (slug, title, content_key, requires_access, sort_order)
VALUES
  ('podcasts', 'Подкасты', 'menu.materials.podcasts', TRUE, 10),
  ('practices', 'Практики', 'menu.materials.practices', TRUE, 20),
  ('challenges', 'Челленджи', 'menu.materials.challenges', TRUE, 30),
  ('archive', 'Архив недель', 'menu.materials.archive', TRUE, 40)
ON CONFLICT (slug) DO UPDATE
  SET title = EXCLUDED.title,
      content_key = EXCLUDED.content_key,
      requires_access = EXCLUDED.requires_access,
      sort_order = EXCLUDED.sort_order,
      updated_at = NOW();

INSERT INTO material_categories (slug, title, content_key, parent_id, requires_access, sort_order)
SELECT 'archive.week1', 'Неделя 1', 'menu.materials.archive.week1', id, TRUE, 41
FROM material_categories
WHERE slug = 'archive'
ON CONFLICT (slug) DO UPDATE
  SET title = EXCLUDED.title,
      content_key = EXCLUDED.content_key,
      parent_id = EXCLUDED.parent_id,
      requires_access = EXCLUDED.requires_access,
      sort_order = EXCLUDED.sort_order,
      updated_at = NOW();

-- =========================
-- Конец schema.sql v3.1
-- =========================
