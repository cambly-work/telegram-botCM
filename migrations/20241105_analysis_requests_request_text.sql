BEGIN;

ALTER TABLE analysis_requests
    ADD COLUMN IF NOT EXISTS request_text TEXT;

UPDATE analysis_requests
   SET request_text = NULLIF(
        COALESCE(NULLIF(preferred_format, ''), '') ||
        CASE
            WHEN preferred_time IS NOT NULL AND preferred_time <> '' AND preferred_format IS NOT NULL AND preferred_format <> ''
                THEN E'\n\n' || preferred_time
            WHEN preferred_time IS NOT NULL AND preferred_time <> ''
                THEN preferred_time
            ELSE ''
        END,
        ''
    )
 WHERE request_text IS NULL OR request_text = '';

UPDATE analysis_requests
   SET request_text = 'Запрос не указан'
 WHERE request_text IS NULL OR request_text = '';

ALTER TABLE analysis_requests
    ALTER COLUMN request_text SET NOT NULL;

ALTER TABLE analysis_requests
    ALTER COLUMN contact DROP NOT NULL;

ALTER TABLE analysis_requests
    DROP COLUMN IF EXISTS preferred_format,
    DROP COLUMN IF EXISTS preferred_time;

COMMIT;
