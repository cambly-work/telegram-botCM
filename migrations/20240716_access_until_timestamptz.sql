DO $$
BEGIN
  IF EXISTS (
    SELECT 1
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'users'
       AND column_name = 'access_until'
       AND udt_name = 'timestamp'
  ) THEN
    EXECUTE $$
      ALTER TABLE users
        ALTER COLUMN access_until TYPE timestamptz
        USING timezone('UTC', access_until);
    $$;
  END IF;

  IF EXISTS (
    SELECT 1
      FROM information_schema.columns
     WHERE table_schema = 'public'
       AND table_name = 'payments'
       AND column_name = 'access_until'
       AND udt_name = 'timestamp'
  ) THEN
    EXECUTE $$
      ALTER TABLE payments
        ALTER COLUMN access_until TYPE timestamptz
        USING timezone('UTC', access_until);
    $$;
  END IF;
END$$;
