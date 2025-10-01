BEGIN;

-- Очистка тестовых записей по tg_user_id, чтобы можно было перезапускать скрипт.
DELETE FROM users WHERE tg_user_id BETWEEN 999000001 AND 999000010;

INSERT INTO users (
    tg_user_id, username, full_name, email, phone, status, access_until, joined_club_at, created_at, updated_at
) VALUES
    (999000001, 'lead_demo', 'Лида Лид', 'lead_demo@example.com', '+79000000001', 'lead_funnel', NULL, NULL, NOW(), NOW()),
    (999000002, 'active_demo', 'Анна Актив', 'active_demo@example.com', '+79000000002', 'member_active', NOW() + INTERVAL '90 days', NOW() - INTERVAL '30 days', NOW(), NOW()),
    (999000003, 'active_forever', 'Фея Вечная', 'forever@example.com', '+79000000003', 'member_active', NULL, NOW() - INTERVAL '200 days', NOW(), NOW()),
    (999000004, 'expired_recent', 'Эля Истекшая', 'expired_recent@example.com', '+79000000004', 'member_expired', NOW() - INTERVAL '5 days', NOW() - INTERVAL '120 days', NOW(), NOW()),
    (999000005, 'expired_long', 'Стелла Старая', 'expired_long@example.com', '+79000000005', 'member_expired', NULL, NOW() - INTERVAL '400 days', NOW(), NOW());

COMMIT;
