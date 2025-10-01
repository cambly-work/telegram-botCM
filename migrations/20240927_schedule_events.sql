-- 20240927: schedule cycle weeks, events and reminders

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

DO $$
BEGIN
  BEGIN
    ALTER TABLE schedule_cycle_weeks
      ADD CONSTRAINT schedule_cycle_weeks_week_number_unique UNIQUE (week_number);
  EXCEPTION WHEN duplicate_object THEN
    NULL;
  END;
END$$;

CREATE INDEX IF NOT EXISTS idx_schedule_cycle_weeks_active
  ON schedule_cycle_weeks(is_archived, start_date NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_schedule_cycle_weeks_dates
  ON schedule_cycle_weeks(start_date, end_date);

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

CREATE INDEX IF NOT EXISTS idx_schedule_events_active
  ON schedule_events(is_archived, scheduled_at);

CREATE INDEX IF NOT EXISTS idx_schedule_events_week
  ON schedule_events(week_id);

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

CREATE INDEX IF NOT EXISTS idx_schedule_event_reminders_due
  ON schedule_event_reminders(remind_at)
  WHERE is_cancelled = FALSE AND notified_at IS NULL;
