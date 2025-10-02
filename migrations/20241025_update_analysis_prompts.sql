-- Обновление текстов заявки на разбор: формат, ретраи и подтверждение.
INSERT INTO content_versions (key, value, updated_at)
SELECT 'menu.analysis.format_prompt', value, NOW()
FROM content
WHERE key = 'menu.analysis.format_prompt';

UPDATE content
SET value = 'Расскажи, как тебе удобно провести разбор. Укажи желаемую дату/время и контакт для связи.',
    updated_at = NOW()
WHERE key = 'menu.analysis.format_prompt';

INSERT INTO content_versions (key, value, updated_at)
VALUES (
    'menu.analysis.format_prompt',
    'Расскажи, как тебе удобно провести разбор. Укажи желаемую дату/время и контакт для связи.',
    NOW()
);

INSERT INTO content_versions (key, value, updated_at)
SELECT 'menu.analysis.format_retry', value, NOW()
FROM content
WHERE key = 'menu.analysis.format_retry';

UPDATE content
SET value = 'Нужны желаемые дата/время и контакт, чтобы запланировать разбор. Напиши эти данные.',
    updated_at = NOW()
WHERE key = 'menu.analysis.format_retry';

INSERT INTO content_versions (key, value, updated_at)
VALUES (
    'menu.analysis.format_retry',
    'Нужны желаемые дата/время и контакт, чтобы запланировать разбор. Напиши эти данные.',
    NOW()
);

INSERT INTO content_versions (key, value, updated_at)
SELECT 'menu.analysis.confirm_prompt', value, NOW()
FROM content
WHERE key = 'menu.analysis.confirm_prompt';

UPDATE content
SET value = E'Проверь заявку:\n• Детали запроса: {format}\n• Контакт: {contact}\n• Время: {time}',
    updated_at = NOW()
WHERE key = 'menu.analysis.confirm_prompt';

INSERT INTO content_versions (key, value, updated_at)
VALUES (
    'menu.analysis.confirm_prompt',
    E'Проверь заявку:\n• Детали запроса: {format}\n• Контакт: {contact}\n• Время: {time}',
    NOW()
);
