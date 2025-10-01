from keyboards import (
    ADMIN_BEHAVIOR_BUTTON,
    ADMIN_BEHAVIOR_ONBOARDING,
    ADMIN_BEHAVIOR_REGISTRATION,
    ADMIN_BEHAVIOR_START,
    ADMIN_BROADCAST_BUTTON,
    ADMIN_SCHEDULE_BUTTON,
    ADMIN_BROADCAST_HISTORY_BUTTON,
    ADMIN_BROADCAST_REMINDER_TEXT,
    ADMIN_CONTENT_MENU,
    ADMIN_TEXTS_ENTRY,
    ADMIN_DEBUG_BUTTON,
    ADMIN_PAYMENTS_BUTTON,
    ADMIN_PAYMENTS_CLOSE_WINDOW,
    ADMIN_PAYMENTS_CONFIRM_ACCESS,
    ADMIN_PAYMENTS_MARK_FAILED,
    ADMIN_PAYMENTS_MARK_PAID,
    ADMIN_PAYMENTS_OPEN_WINDOW,
    ADMIN_PAYMENTS_REVOKE_ACCESS,
    ADMIN_PAYMENTS_SHOW_LATEST,
    ADMIN_SETTINGS_BUTTON,
    ADMIN_STATS_BUTTON,
    ADMIN_USERS_BUTTON,
    BACK_TO_ADMIN,
    BACK_TO_BEHAVIOR,
    BACK_TO_MAIN,
    BROADCAST_ALL_BUTTON,
    BROADCAST_EXPIRED_BUTTON,
    BROADCAST_LEADS_BUTTON,
    BROADCAST_HISTORY_MORE_BUTTON,
    BROADCAST_MEMBERS_BUTTON,
    BROADCAST_TEMPLATES_BUTTON,
    LEARNING_PROGRESS_BUTTON,
    MATERIALS_CATALOG_BUTTON,
    MATERIALS_PRACTICES_BUTTON,
    MATERIALS_CHALLENGES_BUTTON,
    materials_menu_keyboard,
    learning_menu_keyboard,
    admin_behavior_keyboard,
    admin_broadcast_keyboard,
    admin_main_keyboard,
    admin_payments_keyboard,
    admin_settings_keyboard,
)


def _keyboard_texts(markup):
    return [[button.text for button in row] for row in markup.keyboard]


def test_admin_broadcast_keyboard_includes_status_flags():
    statuses = {
        "Напоминания анкет": True,
        "Напоминания уроков": False,
        "Напоминания об окончании доступа": True,
    }

    rows = _keyboard_texts(admin_broadcast_keyboard(statuses))

    assert rows[0] == [BROADCAST_ALL_BUTTON, BROADCAST_LEADS_BUTTON]
    assert rows[1] == [BROADCAST_MEMBERS_BUTTON, BROADCAST_EXPIRED_BUTTON]
    assert rows[2] == [BROADCAST_TEMPLATES_BUTTON, ADMIN_BROADCAST_HISTORY_BUTTON]
    assert rows[3] == [BROADCAST_HISTORY_MORE_BUTTON]
    assert rows[4] == [ADMIN_BROADCAST_REMINDER_TEXT]
    assert rows[5] == ["✅ Напоминания анкет"]
    assert rows[6] == ["❌ Напоминания уроков"]
    assert rows[7] == ["✅ Напоминания об окончании доступа"]
    assert rows[8] == [BACK_TO_ADMIN, BACK_TO_MAIN]


def test_admin_main_keyboard_layout():
    rows = _keyboard_texts(admin_main_keyboard())
    assert rows == [
        [ADMIN_USERS_BUTTON],
        [ADMIN_SCHEDULE_BUTTON],
        [ADMIN_BROADCAST_BUTTON, ADMIN_CONTENT_MENU],
        [ADMIN_BEHAVIOR_BUTTON, ADMIN_SETTINGS_BUTTON],
        [ADMIN_STATS_BUTTON, ADMIN_DEBUG_BUTTON],
        [BACK_TO_MAIN],
    ]
    flattened = [text for row in rows for text in row]
    assert ADMIN_PAYMENTS_BUTTON not in flattened


def test_admin_behavior_keyboard_contains_payments_button():
    rows = _keyboard_texts(admin_behavior_keyboard())
    assert rows == [
        [ADMIN_BEHAVIOR_START],
        [ADMIN_BEHAVIOR_REGISTRATION],
        [ADMIN_BEHAVIOR_ONBOARDING],
        [ADMIN_PAYMENTS_BUTTON],
        [BACK_TO_ADMIN, BACK_TO_MAIN],
    ]


def test_admin_payments_keyboard_back_navigation():
    rows_open = _keyboard_texts(admin_payments_keyboard(payments_open=True))
    assert rows_open[0] == [ADMIN_PAYMENTS_CLOSE_WINDOW]
    assert rows_open[1] == [ADMIN_PAYMENTS_SHOW_LATEST]
    assert rows_open[2] == [ADMIN_PAYMENTS_CONFIRM_ACCESS, ADMIN_PAYMENTS_REVOKE_ACCESS]
    assert rows_open[3] == [ADMIN_PAYMENTS_MARK_PAID, ADMIN_PAYMENTS_MARK_FAILED]
    assert rows_open[4] == [BACK_TO_BEHAVIOR, BACK_TO_ADMIN]
    assert rows_open[5] == [BACK_TO_MAIN]

    rows_closed = _keyboard_texts(admin_payments_keyboard(payments_open=False))
    assert rows_closed[0] == [ADMIN_PAYMENTS_OPEN_WINDOW]
    assert rows_closed[4] == [BACK_TO_BEHAVIOR, BACK_TO_ADMIN]
    assert rows_closed[5] == [BACK_TO_MAIN]


def test_learning_menu_keyboard_layout():
    rows = _keyboard_texts(learning_menu_keyboard())

    assert rows == [
        ["Бесплатные уроки", LEARNING_PROGRESS_BUTTON],
        ["Окно в Магнетизм", "Записаться на разбор"],
        ["Пройти тест"],
        [BACK_TO_MAIN],
    ]


def test_materials_menu_keyboard_all_sections_available():
    rows = _keyboard_texts(
        materials_menu_keyboard(weekly_enabled=True, schedule_enabled=True)
    )
    assert rows == [
        ["Материалы недели", MATERIALS_CATALOG_BUTTON],
        [MATERIALS_PRACTICES_BUTTON, MATERIALS_CHALLENGES_BUTTON],
        ["Расписание"],
        [BACK_TO_MAIN],
    ]


def test_materials_menu_keyboard_highlights_locked_sections():
    rows = _keyboard_texts(
        materials_menu_keyboard(weekly_enabled=False, schedule_enabled=False)
    )
    assert rows[0][0] == "Материалы недели 🔒"
    assert rows[0][1] == MATERIALS_CATALOG_BUTTON
    assert rows[1] == [MATERIALS_PRACTICES_BUTTON, MATERIALS_CHALLENGES_BUTTON]
    assert rows[2] == ["Расписание 🔒"]
    assert rows[3] == [BACK_TO_MAIN]


def test_materials_menu_keyboard_mixed_flags():
    rows = _keyboard_texts(
        materials_menu_keyboard(weekly_enabled=True, schedule_enabled=False)
    )
    assert rows[0] == ["Материалы недели", MATERIALS_CATALOG_BUTTON]
    assert rows[1] == [MATERIALS_PRACTICES_BUTTON, MATERIALS_CHALLENGES_BUTTON]
    assert rows[2] == ["Расписание 🔒"]
    assert rows[3] == [BACK_TO_MAIN]


def test_admin_settings_keyboard_no_content_shortcuts():
    flags = {
        "payments_open": True,
        "payments_manual_review": False,
        "show_weekly_materials": True,
        "show_schedule": False,
    }
    labels = {
        "payments_open": "Окно оплаты",
        "payments_manual_review": "Ручная проверка оплат",
        "show_weekly_materials": "Материалы недели",
        "show_schedule": "Расписание",
    }

    rows = _keyboard_texts(admin_settings_keyboard(flags, labels))

    assert rows[-1] == [BACK_TO_ADMIN, BACK_TO_MAIN]

    flattened = [text for row in rows for text in row]
    assert ADMIN_CONTENT_MENU not in flattened
    assert ADMIN_TEXTS_ENTRY not in flattened

    assert flattened[0] == "✅ Окно оплаты"
    assert flattened[1] == "❌ Ручная проверка оплат"
    assert flattened[2] == "✅ Материалы недели"
    assert flattened[3] == "❌ Расписание"
